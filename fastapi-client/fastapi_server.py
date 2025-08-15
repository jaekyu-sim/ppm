from fastapi import FastAPI, Request
import uvicorn
from contextlib import asynccontextmanager
 
from mcp_client import MCPClient
from smee_client import SmeeClientManager

mcp_client_instance: MCPClient = None
smee_client_manager: SmeeClientManager = None

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("FastAPI 시작 중...")

    global mcp_client_instance, smee_client_manager

    # Smee 클라이언트 시작
    print("Smee 클라이언트 시작 중...")

    smee_url = "https://smee.io/JsEoOmxPUGyv3cl"
    target_url = "http://localhost:8000/webhook"
    smee_client_manager = SmeeClientManager(smee_url, target_url)
    try:
        await smee_client_manager.start()
    except Exception as e:
        print(f"Smee 클라이언트 시작 실패: {e}")

    mcp_client_instance = MCPClient()

    # MCP 서버 연결
    print("MCP 서버에 연결 시도...")

    try:
        await mcp_client_instance.connect_to_server("fastmcp-server/mcp_server.py")
        print("MCP 서버 연결 성공.")
    except Exception as e:
        print(f"MCP 서버 연결 실패: {e}")

    yield
    # FastAPI 종료 시 MCP 클라이언트 리소스 정리
    print("FastAPI 종료 중, MCP 클라이언트 정리...")
    await mcp_client_instance.cleanup()
    if smee_client_manager:
        await smee_client_manager.stop()
    print("MCP 클라이언트 정리 완료.")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
   return {"message": "FastAPI 서버가 실행 중입니다!"}

@app.get("/tools")
async def get_mcp_tools():
    if not mcp_client_instance or not mcp_client_instance.session:
        return {"error": "MCP 클라이언트가 연결되지 않았습니다."}, 500

    try:
        response = await mcp_client_instance.session.list_tools()
        tool_names = [tool.name for tool in response.tools]
        return {"tools": tool_names}
    except Exception as e:
        return {"error": f"MCP 도구 목록 조회 중 오류 발생: {e}"}, 500

@app.post("/webhook")
async def github_webhook(request: Request):
    data = await request.json()
    # Process the webhook payload
    # TODO: api_client.py 코드 옮기기
    print("Received webhook:", data)
    return {"status": "ok"}


if __name__ == "__main__":
    # Uvicorn을 사용하여 FastAPI 애플리케이션 실행
   uvicorn.run(app, host="0.0.0.0", port=8000)