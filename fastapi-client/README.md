### FastAPI client 구동 준비사항
1. Smee 클라이언트 설치
```bash
npm install --global smee-client
```
2. HTTP 메시지 테스트(`test.http`) 를 위한 'REST client' 확장 프로그램 설치

### FastAPI client 구동 방법
```bash
python fastapi-client/api_client.py
```

### FastAPI client Flow
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

### API Endpoints
1. `GET /` : root, endpoint 목록 반환
2. `GET /health` : Health check
3. `POST /webhook` : Github Push 이벤트 Webhook 수신
    - https://smee.io/JsEoOmxPUGyv3cl 에서 'Redeliver this payload' 수행
    - Github Settings - Webhook - Recent Deliveries 에서도 재전송 가능, admin 문제로 해당 메뉴 접근 불가 시 위의 방법으로 수행