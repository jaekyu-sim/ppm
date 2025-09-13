import json
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
#import asyncio

from graph.node import code_interpreter, compare_to_rfp
from graph.build import create_code_compare_to_rfp_graph
from graph.state import AgentState
from result_processor import process_code_comparison_result
from github_service import get_pr_changed_files_content, get_commit_changed_files_content


smee_client_manager: SmeeClientManager = None

vector_store, _embeddings = load_or_build_vector_store()

retriever = vector_store.as_retriever(search_kwargs={'k': 1})

llm = ChatOllama(model="qwen3:4b", temperature=0.2)

#req_check_graph = create_req_check_graph(vector_store, llm, top_k=5)

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

@app.post("/webhook")
async def github_webhook(request: Request):
    data = await request.json()
    event_type = request.headers.get('X-GitHub-Event')

    try:
        repo_full_name = None
        pr_number = None
        commit_sha = None

        commitResult = None

        if event_type == 'push':
            print("Push 이벤트 수신")

            repo_full_name = data['repository']['full_name']
            commit_sha = data['head_commit']['id']
            print(f"Webhook 처리 시작: {repo_full_name}, Commit SHA: {commit_sha}")
            
            commitResult = get_commit_changed_files_content(repo_full_name, commit_sha)

        elif event_type == 'pull_request':
            print("Pull Request 이벤트 수신")

            repo_full_name = data['repository']['full_name']
            pr_number = data['number']
            commit_sha = data['pull_request']['head']['sha']
            print(f"Webhook 처리 시작: {repo_full_name}, PR: #{pr_number}, Commit SHA: {commit_sha}")
            
            commitResult = get_pr_changed_files_content(repo_full_name, pr_number)
        
        else:
            print(f"지원하지 않는 이벤트 타입입니다: {event_type}")
            return {"status": "ignored", "message": f"Unsupported event type: {event_type}"}

        if not commitResult or not commitResult.get('file_list'):
            return {"status": "error", "message": "커밋 데이터 조회에 실패했습니다."}

        
        # RAG 불러오기.
        file_list = commitResult['file_list']
        all_answers = []
        
        graph = create_code_compare_to_rfp_graph()
        compare_result = graph.invoke({'file_code': file_list})

        print("==============================================================")
        print("FINAL RESULT : ", compare_result)
        
        if compare_result and 'answer' in compare_result:
            all_answers.extend(compare_result['answer'])

        # for i in range(len(file_list)):
        #     file_path = file_list[i]['fileName']
        #     file_code = file_list[i]['code']
            
        #     # code_interpreter_prompt = PromptTemplate.from_template(code_interpreter_template)
        #     # code_interpreter_result_chain = code_interpreter_prompt | llm | StrOutputParser()
        #     # result = code_interpreter_result_chain.invoke({"information": file_code})
        #     #print("code_interpreter node 실행 시작")
        #     state = AgentState(file_code=file_list[i]['code'])

    
        #     # # NODE 1 시작
        #     # result = code_interpreter(state)
        #     # result = result['answer']

        #     # # NODE 2 시작
        #     # state = AgentState(answer=result)
        #     # answ = compare_to_rfp(state)
        #     # print("*** sss *** sss : ", answ)

        #     graph = create_code_compare_to_rfp_graph()
        #     compare_result = graph.invoke({'file_code': file_list[i]['code']})
        #     print("==============================================================")
        #     print("FINAL RESULT : ", compare_result)
            
        #     if compare_result and 'answer' in compare_result:
        #         all_answers.extend(compare_result['answer'])

        final_result = {'answer': all_answers}
        
        pr_comment_send = data.get('pr_comment_send', True)
        pr_number = data['number']

        result_markdown = await process_code_comparison_result(final_result, repo_full_name, pr_comment_send, pr_number)

        return Response(content=result_markdown, media_type="text/markdown")
    
    except KeyError as e:
        print(f"Webhook payload에서 필요한 키를 찾을 수 없습니다: {e}")
        return {"status": "error", "message": f"Missing key in webhook payload: {e}"}
    except Exception as e:
        print(f"Webhook 처리 중 오류 발생: {e}")
        return {"status": "error", "message": str(e)}

    

if __name__ == "__main__":
    # Uvicorn을 사용하여 FastAPI 애플리케이션 실행
   uvicorn.run(app, host="0.0.0.0", port=8000)
   