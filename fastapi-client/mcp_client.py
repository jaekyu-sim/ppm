from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from langchain_ollama.chat_models import ChatOllama
from langchain_core.messages import HumanMessage


class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_server(self, server_script_path: str):

        if not server_script_path.endswith('.py'):
            raise ValueError("Server script must be a .py file")
            
        server_params = StdioServerParameters(
            command="python",
            args=[server_script_path],
            env=None
        )
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        
        # List available tools
        response = await self.session.list_tools()
        print("\nConnected to server with tools:", [tool.name for tool in response.tools])

    async def process_query(self, query: str) -> str:

        llm = ChatOllama(
            model="qwen3:4b",
            temperature=0.8
        )   

        tool_response = await self.session.list_tools()
        available_tools = [{ 
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in tool_response.tools]

        llm_with_tools = llm.bind_tools(available_tools)

        messages = [HumanMessage(content=query)]
        print('Query:', query)

        # Initial Call LLM
        init_response = llm_with_tools.invoke(messages)
        # print("Initial response:", init_response)

        if init_response.tool_calls:
            tool_call = init_response.tool_calls[-1]
            # print(f"Executing tool: {tool_call['name']} with args: {tool_call['args']}")
            tool_response = await self.session.call_tool(tool_call['name'], tool_call['args'])

        if not tool_response.isError:
            # print("Tool response:", tool_response.structuredContent)
            return tool_response.structuredContent
        else:
            # print("Error in tool response:", tool_response.content[-1].text)
            return False


    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()