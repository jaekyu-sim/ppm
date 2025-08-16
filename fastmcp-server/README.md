# FastMCP 서버
- GitHub Webhook 이벤트를 수신하여 MCP 서버와 상호작용하는 브리지 역할
- Smee.io를 통해 웹훅을 수신하고, 이를 처리하여 MCP 서버에 필요한 작업 요청



## 1. 실행 방법
```bash
mcp dev .\fastmcp-server\mcp_server.py
# 위 대로 실행 할 경우, 6277 port 로 서비스, 6274 port 로 inspector 가 실행 됨.
```

## 2. 구성 요소
   - mcp_server.py: mcp_server.ipynb 에서 기능 구현 및 테스트 완료 되면 --> 로직 옮겨서 구동하는 서버 부분
   - mcp_server.ipynb: mcp server logic 에 들어가는 내용에 대해, 구현하고 테스트 해보는 부분. 
   - chorma_db 폴더: docs 폴더 내용이 vector db 화 하여 저장되는 부분
   - docs 폴더 : RAG 할 문서 저장해둔 폴더
   - prompt_by_models : 모델마다 구동 잘 되는 프롬프트가 별도로 존재하여, 해당 폴더에 모델 별로 프롬프트 정리해서 쓸 용도로 생성 한 폴더. (필요 없으면 삭제 해도 됨.)



---

