import asyncio
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

llmwiki = MCPServerStdio(
    command="/home/deepak/Jade/llmwiki/mcp/.venv/bin/python",
    args=[
        "/home/deepak/Jade/llmwiki/llmwiki",
        "mcp",
        "/home/deepak/Jade/research",
    ],
)

agent = Agent(
    "claude-sonnet-4-6",
    mcp_servers=[llmwiki],
    system_prompt="You are a research assistant with access to an LLM Wiki knowledge base.",
)

async def main():
    async with agent.run_mcp_servers():
        result = await agent.run(
            "Search for calibration schema and summarise the required fields."
        )
        print(result.data)

asyncio.run(main())
