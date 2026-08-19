import asyncio
from tyrion_ai.env import openai_compatible_config_from_env
from tyrion_ai.openai_compatible import OpenAICompatibleProvider
from tyrion_agent.messages import UserMessage

async def main():
    config = openai_compatible_config_from_env()
    provider = OpenAICompatibleProvider(config)
    messages = [UserMessage(content="Hello!")]
    
    async for event in provider.stream_response(
        model="openai/gpt-4o-mini",
        system="You are a helpful assistant.",
        messages=messages,
        tools=[]
    ):
        print(event.type, repr(getattr(event, "delta", "")))

if __name__ == "__main__":
    asyncio.run(main())
