# 가상환경 실행 : .\.venv\Scripts\activate.ps1

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ppm")

@mcp.tool()
def add(a: int, b: int) -> int:
    """두 숫자를 더합니다."""
    return a + b

# dev : mcp dev ./fastmcp-server/mcp_server.py
# prd : python ./fastmcp-server/mcp_server.py 
if __name__ == "__main__":
    mcp.run(transport="stdio")