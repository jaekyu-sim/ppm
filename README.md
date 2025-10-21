# PPM Agent

AX Young Talent Project

AI 기반 개발 진척도 자동 추적 시스템

## 1. 핵심 아이디어 개요
개발자의 GitHub Pull Request를 AI가 자동 분석하여 요구사항 대비 개발 진척도를 실시간으로 측정하고 PM에게 리포팅하는 시스템

## 2. 개발 환경 설정
### 2-1. github webhook 설정
1) PPM Agent의 smee.io로 Webhook 연결
2) 연결하고자 하는 Repository의 `Settings > Webhooks`에서 `Add webhook` 로 다음 정보로 추가

``` 
Payload URL: https://smee.io/JsEoOmxPUGyv3cl
Content type: application/json
SSL verification: Disable
Which events would you like to trigger this webhook?: Send me everything.
```


### 2-2. ollama 설치 및 설정
1) 성능 향상을 위한 환경변수 설정
```text
OLLAMA_CONTEXT_LENGTH=8192
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
```

2) [ollama](https://ollama.com/download) 설치 후 CLI로 모델 download 및 기동
- 우측 하단 상태표시줄에 ollama GUI 종료 후 터미널의 CLI로 실행
```bash
ollama pull qwen3:4b-instruct-2507-q8_0
ollama serve
```

### 2-3. 프로젝트 설정 및 실행
1) `fastapi_client/docs/vector_db_rfp_data.json` 에 요구사항 정의

2) `fastapi_client/.env` 파일에 Pull Request에 결과를 등록해줄 PPM-Bot(임의의 github 계정)의 [토큰](https://github.com/settings/tokens) 입력

**fastapi_client/.env**
```bash
# Smee.io webhook URL
SMEE_URL=https://smee.io/JsEoOmxPUGyv3cl

# MCP Server URL
MCP_SERVER_URL=http://localhost:8001

# PPM-Bot GitHub Token
GITHUB_TOKEN="" # 계정에 생성한 토큰 값 입력
```

3) 프로젝트 의존성 패키지 설치 및 실행

**uv 를 이용한 설치**
```bash
# uv 미설치 시 설치
pip install uv

# uv 를 통한 의존성 패키지 설치
uv sync

# 실행
uv run python fastapi_client/fastapi_server.py
```

**기존 방식을 이용한 설치**
```bash
# Python 가상 환경 설정 (프로젝트 루트에서 실행)
python -m venv .venv

# 가상환경 진입
## macOS/Linux 
source .venv/bin/activate  

## Windows
source .venv/Scripts/activate  

# 의존성 패키지 설치
pip install -r requirements.txt

# 실행
python fastapi_client/fastapi_server.py
```
### 2-4. 테스트
<img alt="테스트 양식" src="https://github.com/user-attachments/assets/e5556a49-4e2e-44a7-a0ab-064107a473e1" />

- `test/ppm_test/ppm_test.http` 에서 테스트 진행

### 2-5. 결과
- github 의 해당 Pull Request 의 comment 에 다음과 같이 개발 진척도 결과가 등록됨

<img alt="개발 진척도 결과" src="https://github.com/user-attachments/assets/1c705f2f-a5d0-45f8-bf0f-b04382aa0719" />

## 4. 시스템 동작 방식
<img alt="시스템 동작 방식" src="https://github.com/user-attachments/assets/ebe36045-c1a2-4f59-8cb1-0ad269c783a9">

