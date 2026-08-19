"""OpenAI compatible chat completions provider."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from tyrion_agent.messages import (
    AgentMessage,
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from tyrion_agent.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from tyrion_agent.tools import AgentTool
from tyrion_ai.env import OpenAICompatibleConfig
from tyrion_ai.http import create_http_client


class OpenAICompatibleProvider:
    """Provider for OpenAI-compatible /chat/completions APIs."""

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        self._config = config
        self._client = create_http_client(
            base_url= config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds
        )
    def stream_response(
            self,
            *,
            model: str,
            system :str,
            messages :list[AgentMessage],
            tools :list[AgentTool],
            signal :object | None = None,
    ) -> AsyncIterator[AssistantMessageEvent]:
        """Stream a chat completion response."""
        return self._stream(model, system, messages, tools)
    async def _stream(
            self,
            model: str,
            system :str,
            messages :list[AgentMessage],
            tools :list[AgentTool],
    ) -> AsyncIterator[AssistantMessageEvent]:
        # 1. Build the request payload
        payload = self._build_payload(model, system, messages, tools)

        # 2. Make the streaming HTTP request
        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    error_msg = f"API error {response.status_code} : {body.decode()}"
                    yield AssistantErrorEvent(
                        error = AssistantMessage(
                            model = model,
                            content = [],
                            stop_reason= "error",
                            error_message = error_msg,
                        )
                    )
                    return
                async for event in self._parse_sse_stream(response, model):
                    yield event

        except httpx.HTTPError as exc:
            yield AssistantErrorEvent(
                error = AssistantMessage(
                    model = model,
                    content = [],
                    stop_reason= "error",
                    error_message=f"HTTP error: {exc}",
                )
            )

    ## Converting our types into OpenAI JSON format

    def _build_payload(
            self,
            model:str,
            system :str,
            messages :list[AgentMessage],
            tools :list[AgentTool],
    ) -> dict[str, Any]:
        """Build the OpenAI chat completions request body."""
        openai_messages : list[dict[str, Any]] = []

        # System Prompt
        openai_messages.append({"role" : "system", "content" : system})
        # Convert each transcript message to OpenAI format
        for msg in messages:
            if isinstance(msg, UserMessage):
                openai_messages.append({
                    "role" : "user",
                    "content" : msg.content,
                })
            elif isinstance(msg, AssistantMessage):
                openai_msg :dict[str, Any] = {
                    "role" :"assistant",
                    "content" : msg.text or None,
                }
                # Add tools if present
                if msg.tool_calls:
                    openai_msg["tool_calls"] = [
                        {
                            "id" :tc.id,
                            "type" : "function",
                            "function": {
                                "name" :tc.name,
                                "arguments" : json.dumps(tc.arguments),
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                openai_messages.append(openai_msg)
            elif isinstance(msg, ToolResultMessage):
                openai_messages.append({
                    "role" : "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content" :msg.text,
                })
        payload : dict[str, Any] ={
            "model" :model,
            "messages" :openai_messages,
            "stream" :True,
        }

        if tools:
             
            payload["tool_choice"] = "auto"
            payload["tools"] = [
                {
                    "type":"function",
                    "function" :{
                        "name" : tool.name,
                        "description" : tool.description,
                        "parameters" : dict(tool.parameters),
                    }
                }
                for tool in tools
            ]
        return payload


    ## SSE Stream parsing
    partial = None

    async def _parse_sse_stream(
            self,
            response: httpx.Response,
            model : str,
    ) -> AsyncIterator[AssistantMessageEvent]:
        """Parse OpenAI's Server-Sent Events stream into Tyrion events."""

        # We build up the message as the chunks arrive
        text_so_far = ""
        tool_calls_so_far : dict[int, dict[str, Any]] = {}
        started = False

        async for line in response.aiter_lines():
            # SSE Format: each chunk is "data: {json}\n\n"
            if not line.startswith("data: "):
                continue
            data = line[6:]

            if data == "[DONE]":
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            #Extract the delta from the chunk
            choices = chunk.get("choices", [])
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # --- Build the partial message for events ---
            if "content" in delta and delta["content"]:
                text_so_far += delta["content"]

                partial = self._build_partial(model, text_so_far, tool_calls_so_far)

                if not started:
                    started = True
                    yield AssistantStartEvent(partial = partial)

                yield TextDeltaEvent(delta= delta["content"], partial = partial)

                # Tool call deltas
            if "tool_calls" in delta:
                for tc_delta in delta["tool_calls"]:
                    index = tc_delta["index"]
                    if index not in tool_calls_so_far:
                        # New tool call starting
                        tool_calls_so_far[index] = {
                            "id": tc_delta.get("id", ""),
                            "name": tc_delta.get("function", {}).get("name", ""),
                            "arguments": "",
                        }
                        partial = self._build_partial(
                            model, text_so_far, tool_calls_so_far
                        )
                        if not started:
                            started = True
                            yield AssistantStartEvent(partial=partial)
                        yield ToolCallStartEvent(
                            tool_call=ToolCall(
                                id=tool_calls_so_far[index]["id"],
                                name=tool_calls_so_far[index]["name"],
                            ),
                            partial=partial,
                        )
                    else:
                        # Existing tool call — accumulate argument chunks
                        arg_delta = tc_delta.get("function", {}).get("arguments", "")
                        tool_calls_so_far[index]["arguments"] += arg_delta
                        partial = self._build_partial(
                            model, text_so_far, tool_calls_so_far
                        )
                        yield ToolCallDeltaEvent(
                            delta=arg_delta,
                            tool_call=ToolCall(
                                id=tool_calls_so_far[index]["id"],
                                name=tool_calls_so_far[index]["name"],
                            ),
                            partial=partial,
                        )
            # Finish — emit end events for tool calls and the final message
            if finish_reason is not None:
                final = self._build_final(model, text_so_far, tool_calls_so_far, finish_reason)

                if not started:
                    started = True
                    yield AssistantStartEvent(partial=partial)

                for tc_data in tool_calls_so_far.values():
                    args = self._safe_parse_arguments(tc_data["arguments"])
                    yield ToolCallEndEvent(
                        tool_call=ToolCall(
                            id = tc_data["id"],
                            name = tc_data["name"],
                            arguments=args,
                        ),
                        partial=final
                    )
                yield AssistantDoneEvent(message = final)
                return 
        if started:
            final = self._build_final(model, text_so_far, tool_calls_so_far, "stop")
            yield AssistantDoneEvent(message=final)
        else:
            yield AssistantErrorEvent(
                error = AssistantMessage(
                    model = model,
                    content =[],
                    stop_reason="error",
                    error_message = "Provider returned empty reponse",                    
                )
            )
    ## helpers:

    def _build_partial(
            self,
            model: str,
            text :str,
            tool_calls : dict[int, dict[str, Any]],
    ) -> AssistantMessage:
        """Build a partial Assistant Message from accumulators."""
        content: list[TextContent | ToolCall] =[]
        if text:
            content.append(TextContent(text = text))
        for tc_data in tool_calls.values():
            args = self._safe_parse_arguments(tc_data["arguments"])
            content.append(ToolCall(
                id = tc_data["id"],
                name = tc_data["name"],
                arguments = args
            ))
        return AssistantMessage(model = model, content = content)
    def _build_final(
            self,
            model: str,
            text: str,
            tool_calls: dict[int, dict[str, Any]],
            finish_reason: str,
    ) -> AssistantMessage:
        """Build the final AssistantMessage."""
        content : list[TextContent | ToolCall] = []
        if text:
            content.append(TextContent(text = text))
        for tc_data in tool_calls.values():
            args = self._safe_parse_arguments(tc_data["arguments"])
            content.append(ToolCall(
                id=tc_data["id"],
                name=tc_data["name"],
                arguments=args,
            ))
        stop_reason = "toolUse" if tool_calls else "stop"
        return AssistantMessage(
            model=model,
            content = content,
            stop_reason=stop_reason
        )
    def _safe_parse_arguments(self, raw: str) -> dict[str, Any]:
        """Parse JSON arguments string, returning empty dict on failure."""
        if not raw:
            return {}
        try:
            result = json.loads(raw)
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}