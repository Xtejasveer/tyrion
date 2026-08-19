import asyncio
from tyrion_ai.env import OpenAICompatibleConfig
from tyrion_ai.openai_compatible import OpenAICompatibleProvider
from tyrion_agent.messages import UserMessage
from tyrion_coding.tools import create_coding_tools

config = OpenAICompatibleConfig(base_url="http://dummy", api_key="dummy")
provider = OpenAICompatibleProvider(config)
messages = [UserMessage(content="What files are in this directory?")]
tools = create_coding_tools(cwd=".")
payload = provider._build_payload("openai/gpt-4o-mini", "You are tyrion.", messages, tools)

import json
print(json.dumps(payload, indent=2))
