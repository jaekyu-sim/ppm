# FastAPI 서버
- GitHub Webhook 이벤트를 수신하여 MCP 서버와 상호작용하는 브리지 역할
- Smee.io를 통해 웹훅을 수신하고, 이를 처리하여 MCP 서버에 필요한 작업 요청


## 1. 개발 환경 설정
```bash
# Python 가상 환경 설정 (프로젝트 루트에서 실행)
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 의존성 패키지 설치
pip install -r requirments.txt
```
- VS Code REST Client 확장 프로그램 설치 : API 테스트용
- ~smee-client 설치~ : python 3rd-party 로 대체함

## 2. 실행 방법
```bash
python fastapi-client/fastapi_server.py
# FastAPI http://localhost:8000 에서 실행됨
```

## 3. 프로젝트 구조
   - fastapi_server.py: 메인 FastAPI 애플리케이션 로직 및 API 엔드포인트 정의
   - mcp_client.py: MCP 서버와의 연결 및 통신 담당
   - smee_client.py: Smee.io 클라이언트를 관리하여 외부 웹훅을 로컬 서버로 전달
   - (api_client.py) : 코드 이전 후 삭제 예정

## 4. API 엔드포인트 목록
1. `GET /` : root, endpoint 목록 반환
2. `GET /tools` : 현재 연결된 MCP 서버에 등록된 도구(Tool)의 목록 반환
3. `POST /webhook` : Github Push 이벤트 Webhook 수신
    - https://smee.io/JsEoOmxPUGyv3cl 에서 'Redeliver this payload' 수행
    - Github Settings - Webhook - Recent Deliveries 에서도 재전송 가능, admin 문제로 해당 메뉴 접근 불가 시 위의 방법으로 수행

## 5. API 테스트 (test.http 활용)
<img width="1063" height="788" alt="Image" src="https://github.com/user-attachments/assets/5f3ca3c5-bba9-4540-8077-d8355a78fa3d" />


---

### (백업) FastAPI client Flow
1. Github Test Repository 에 push 진행
2. Github에 등록된 Webhook URL 경로로 Push 이벤트 payload 전송
3. 로컬에서 실행 중인 Smee-client로 `/webhook` Request 전달 
4. Push 이벤트 payload 기반으로 Github API 요청하여 수정된 파일 목록과 해당 파일의 전체 소스 가져옴
5. mcp-server로 전달할 데이터 형태로 가공
    ```json
    {
      "author": "sjKang01401",
      "email": "ksj01401@gmail.com",
      "message": "multi file push, LoginService \ucd94\uac00", -- 한글 인코딩 문제 개선 필요
      "sha": "66ba01b050bbc93d4d98b972ccdd7c1eaa282606",
      "files": [
          {
          "fileName": "main/service/LoginService.java",
          "language": "Java",
          "code": "@Service\npublic class LoginService {\n\n    private final UserRepository userRepository;\n\n    public LoginService(UserRepository userRepository) {\n        this.userRepository = userRepository;\n    }\n\n    public boolean login(String email, String password) {\n        return userRepository.findByEmail(email)\n            .map(user -> user.getPassword().equals(password))\n            .orElse(false);\n    }\n}"
          },
          {
          "fileName": "test.txt",
          "language": "Text",
          "code": "push test\npush test 2\npush test 3"
          }
      ]
    }
6. (임시) `MCP_SERVER_URL/analyze_commit` 으로 HTTP Request 전달