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

from mcp_client import MCPClient
from smee_client import SmeeClientManager
import time

from rag_boot import load_or_build_vector_store
#from rag_feature import extract_features, build_query_from_features
#from rag_utils import search_requirements, judge_one
#from req_check_graph import create_req_check_graph
#import asyncio

from graph.node import code_interpreter, compare_to_rfp
from graph.build import create_code_compare_to_rfp_graph
from graph.state import AgentState
from result_processor import process_code_comparison_result


mcp_client_instance: MCPClient = None
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

    # MCP 서버 연결
    print("MCP 서버에 연결 시도...")

    mcp_client_instance = MCPClient()

    try:
        await mcp_client_instance.connect_to_server("fastmcp-server/mcp_server.py")
        print("MCP 서버 연결 성공.")
    except Exception as e:
        print(f"MCP 서버 연결 실패: {e}")

    print("FastAPI 시작.")

    # FastAPI 종료 시 MCP 클라이언트 리소스 정리
    yield
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
    event_type = request.headers.get('X-GitHub-Event')

    repo_full_name = None
    commit_sha = None

    try:
        if event_type == 'push':
            print("Push 이벤트 수신")
            repo_full_name = data['repository']['full_name']
            commit_sha = data['head_commit']['id']

        elif event_type == 'pull_request':
            print("Pull Request 이벤트 수신")
            repo_full_name = data['repository']['full_name']
            commit_sha = data['pull_request']['head']['sha']
        
        else:
            print(f"지원하지 않는 이벤트 타입입니다: {event_type}")
            return {"status": "ignored", "message": f"Unsupported event type: {event_type}"}

        print(f"Webhook 처리 시작: {repo_full_name}, Commit SHA: {commit_sha}")

        query = f"GitHub 리포지토리 '{repo_full_name}'의 커밋 '{commit_sha}'에서 변경된 파일 목록과 각 파일의 전체 내용을 가져와줘."
        start = time.time() # LLM 호출 시간 측정 용. 
        commitResult = await mcp_client_instance.process_query(query) # TODO: process_query 함수 모듈화 or 함수명 변경

        if not commitResult:
            return {"status": "error", "message": "커밋 데이터 조회에 실패했습니다."}
        print(f"LLM Tool Calling Time : {time.time()-start:.4f} sec") # Tool 호출 시간 출력

        
        # RAG 불러오기.
        files = commitResult['files']
        all_answers = []
        
        for i in range(len(files)):
            file_path = files[i]['fileName']
            file_code = files[i]['code']
            
            # code_interpreter_prompt = PromptTemplate.from_template(code_interpreter_template)
            # code_interpreter_result_chain = code_interpreter_prompt | llm | StrOutputParser()
            # result = code_interpreter_result_chain.invoke({"information": file_code})
            #print("code_interpreter node 실행 시작")
            state = AgentState(file_code=files[i]['code'])

    
            # # NODE 1 시작
            # result = code_interpreter(state)
            # result = result['answer']

            # # NODE 2 시작
            # state = AgentState(answer=result)
            # answ = compare_to_rfp(state)
            # print("*** sss *** sss : ", answ)

            graph = create_code_compare_to_rfp_graph()
            compare_result = graph.invoke({'file_code': files[i]['code']})
            print("==============================================================")
            print("FINAL RESULT : ", compare_result)
            
            if compare_result and 'answer' in compare_result:
                all_answers.extend(compare_result['answer'])

        final_result = {'answer': all_answers}
        
        pr_comment_send = data.get('pr_comment_send', True)
        pr_number = data['number']

        result_markdown = await process_code_comparison_result(mcp_client_instance, final_result, repo_full_name, pr_comment_send, pr_number)

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
   