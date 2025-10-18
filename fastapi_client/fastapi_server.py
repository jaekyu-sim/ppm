import json
import asyncio
from datetime import datetime
from typing import Any, Dict
from urllib.parse import parse_qs
from fastapi import FastAPI, HTTPException, Request, Response
from langchain_ollama import ChatOllama
import uvicorn
from contextlib import asynccontextmanager
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
import re
from langchain_core.runnables import RunnableLambda
from statistics import mean
from langchain_core.prompts import PromptTemplate

from smee_client import SmeeClientManager

#from rag_boot import load_or_build_vector_store
from rag_boot_phase2 import load_or_build_vector_store
#from rag_feature import extract_features, build_query_from_features
#from rag_utils import search_requirements, judge_one
#from req_check_graph import create_req_check_graph

from graph.node import code_interpreter, compare_to_rfp
from graph.build import create_code_compare_to_rfp_graph
from graph.state import AgentState
from result_processor import process_code_comparison_result
from github_service import get_pr_changed_files_content, get_commit_changed_files_content

smee_client_manager: SmeeClientManager = None

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("FastAPI 시작 중...")

    global mcp_client_instance, smee_client_manager

    # Smee 클라이언트 시작
    print("Smee 클라이언트 시작 중...")

    smee_url = "https://smee.io/JsEoOmxPUGyv3cl"
    target_url = "http://127.0.0.1:8000/webhook"
    smee_client_manager = SmeeClientManager(smee_url, target_url)
    try:
        await smee_client_manager.start()
    except Exception as e:
        print(f"Smee 클라이언트 시작 실패: {e}")
    print("Smee 클라이언트 시작.")

    print("FastAPI 시작.")

    yield
    print("FastAPI 종료 중...")
    if smee_client_manager:
        await smee_client_manager.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
   return {"message": "FastAPI 서버가 실행 중입니다!"}

def handle_webhook_sync(data: Dict, event_type: str):
    try:
        repo_full_name = None
        pr_number = None
        commit_sha = None
        rfp_number = None
        commitResult = None

        # 이벤트 타입에 따른 소스코드 변경점 조회
        if event_type == 'push':
            print("Push 이벤트 수신")
            repo_full_name = data['repository']['full_name']
            commit_sha = data['head_commit']['id']
            branch_name = data['ref'].split('/')[-1]
            rfp_number = branch_name
            if match := re.match(r"^[A-Z]{3}-\d+", branch_name):
                rfp_number = match.group(0)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Webhook 처리 시작: {repo_full_name}, Commit SHA: {commit_sha}, Branch: {branch_name}, RFP: {rfp_number}")
            commitResult = get_commit_changed_files_content(repo_full_name, commit_sha)

        elif event_type == 'pull_request':
            print("Pull Request 이벤트 수신")
            repo_full_name = data['repository']['full_name']
            pr_number = data['number']
            commit_sha = data['pull_request']['head']['sha']
            branch_name = data['pull_request']['head']['ref']
            rfp_number = branch_name
            if match := re.match(r"^[A-Z]{3}-\d+", branch_name):
                rfp_number = match.group(0)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Webhook 처리 시작: {repo_full_name}, PR: #{pr_number}, Commit SHA: {commit_sha}, Branch: {branch_name}, RFP: {rfp_number}")
            commitResult = get_pr_changed_files_content(repo_full_name, pr_number)
        
        else:
            print(f"지원하지 않는 이벤트 타입입니다: {event_type}")
            return {"status": "ignored", "message": f"Unsupported event type: {event_type}"}

        if not commitResult or not commitResult.get('file_list'):
            return {"status": "error", "message": "커밋 데이터 조회에 실패했습니다."}

        # 소스코드 변경점과 RFP 비교 (LangGraph 호출)
        file_list = commitResult['file_list']
        graph = create_code_compare_to_rfp_graph()
        compare_result = graph.invoke({'file_code': file_list, 'tmp_rfp_number': rfp_number})

        print("==============================================================")
        print("FINAL RESULT : ", compare_result)
        
        # PR 코멘트 전송
        if event_type == 'pull_request':
            pr_comment_send = data.get('pr_comment_send', True)
            pr_comment_debug = data.get('pr_comment_debug', False)
            result_markdown = process_code_comparison_result(
                compare_result, repo_full_name, commit_sha, pr_comment_send, pr_number, pr_comment_debug
            )
            return Response(content=result_markdown, media_type="text/markdown")

        return {"result": compare_result}
    
    except KeyError as e:
        print(f"Webhook payload에서 필요한 키를 찾을 수 없습니다: {e}")
        return {"status": "error", "message": f"Missing key in webhook payload: {e}"}
    except Exception as e:
        print(f"Webhook 처리 중 오류 발생: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/webhook")
async def github_webhook(request: Request):
    data = await request.json()
    event_type = request.headers.get('X-GitHub-Event')
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, handle_webhook_sync, data, event_type)

if __name__ == "__main__":
    # Uvicorn을 사용하여 FastAPI 애플리케이션 실행
   uvicorn.run(app, host="0.0.0.0", port=8000)
   