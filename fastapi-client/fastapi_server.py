import json
from typing import Any, Dict
from urllib.parse import parse_qs
from fastapi import FastAPI, HTTPException, Request
from langchain_ollama import ChatOllama
import uvicorn
from contextlib import asynccontextmanager
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from mcp_client import MCPClient
from smee_client import SmeeClientManager
import time

from rag_boot import load_or_build_vector_store
from rag_feature import extract_features, build_query_from_features
from rag_utils import search_requirements, judge_one
from req_check_graph import create_req_check_graph
import asyncio


mcp_client_instance: MCPClient = None
smee_client_manager: SmeeClientManager = None

vector_store, _embeddings = load_or_build_vector_store()

retriever = vector_store.as_retriever(search_kwargs={'k': 3})

llm = ChatOllama(model="qwen3:4b", temperature=0.2)
req_check_graph = create_req_check_graph(vector_store, llm, top_k=5)

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
    
    try:
        # 코드 변경 내역 불러오기.
        repo_full_name = data['repository']['full_name']
        commit_sha = data['head_commit']['id']
        print(f"Webhook 수신: {repo_full_name}, Commit SHA: {commit_sha}")

        query = f"GitHub 리포지토리 '{repo_full_name}'의 커밋 '{commit_sha}'에서 변경된 파일 목록과 각 파일의 전체 내용을 가져와줘."
        start = time.time() # LLM 호출 시간 측정 용.
        commitResult = await mcp_client_instance.process_query(query) # TODO: process_query 함수 모듈화 or 함수명 변경

        if not commitResult:
            return {"status": "error", "message": "커밋 데이터 조회에 실패했습니다."}
        print(f"LLM Tool Calling Time : {time.time()-start:.4f} sec") # Tool 호출 시간 출력

        
        ## 이후 진행
        # 파일 정보 정리 용 Logging.
        print("===================================================================================================================")
        print("===================================================================================================================")
        print(" * 변경된 파일 갯수 : ", len(commitResult['files']))
        #for i in range(len(commitResult['files'])):
        #    print(str(i+1) + " . " + "변경된 파일 명 : ", commitResult["files"][i]['fileName'])
        #    print(str(i+1) + " . " + "변경된 파일 코드 : ", commitResult["files"][i]['code'])
        
        # RAG 불러오기.
        files = commitResult['files']

        # # 2) 파일별 그래프 실행(동시)
        # async def run_one(f):
        #     file_path = f['fileName']
        #     file_code = f['code']
        #     # LangGraph 호출
        #     state_in = {"file_path": file_path, "code": file_code}
        #     print("1")
        #     result: Dict[str, Any] = await req_check_graph.ainvoke(state_in)
        #     print("1.1")
        #     # 간단 요약
        #     # 최상위 판단 고르기(기본 점수 + confidence)
        #     def _score(j):
        #         base = {"Meets":3, "Partial":2, "Missing":1, "Conflict":0}.get(j["status"],1)
        #         return base + float(j.get("confidence",0))
        #     print("2")
        #     top3 = sorted(result.get("judgments", []), key=_score, reverse=True)[:3]
        #     print("3")
        #     return {
        #         "file": file_path,
        #         "feature_query": result.get("feature_query",""),
        #         "nat_spec": result.get("nat_spec",""),
        #         "judgments_top3": top3,
        #         "all_judgments": result.get("judgments", [])
        #     }
        # print("0")
        # results = await asyncio.gather(*[run_one(f) for f in files])
        # print("4")
        # print(results)

        # return {
        #     "status": "ok",
        #     "repo": repo_full_name,
        #     "commit": commit_sha,
        #     "results": results
        # }
        overall = []
        for i in range(len(files)):
            file_path = files[i]['fileName']
            file_code = files[i]['code']
            code_interpreter_template = """
            당신은 Code Review 전문가입니다.

            지금부터 제공해주는 코드 파일들의 기능을 함수 단위로 분석하세요.
            단순 요약이 아니라, **해당 함수를 개발하기 위해 정의되었을 법한 '요구사항 정의서 수준의 기능 명세'**로 출력하세요.



            information List : {information}

            반드시 아래 규칙을 따르세요:
            - 출력은 아래 형식만 사용합니다.
            - 함수별로 '무엇을 해야 하는지'와 '왜 필요한지', '입력·처리·출력 과정', '예외 처리 조건'을 요구사항 정의 문서처럼 구체적으로 기술하세요.
            - 생각, 분석, 설명, 영어 문장, <think> 등은 절대 포함하지 마세요.
            - 출력은 반드시 한글로만 작성하세요.

            출력 예시:
            <output>
                <func1>
                    - A.java
                    -- [사용자 등록 기능]
                    · 목적: 신규 사용자의 정보를 받아 시스템에 계정을 생성해야 한다.
                    · 입력: 사용자 이름, 이메일, 비밀번호
                    · 처리: 이메일 중복 여부 검사 → 비밀번호 암호화 → DB 저장
                    · 출력: 등록 성공 시 사용자 ID 반환
                    · 예외: 이메일 중복 시 오류 메시지 반환
                </func1>
                <func2>
                    - A.java
                    -- [사용자 삭제 기능]
                    · 목적: 특정 사용자의 계정을 시스템에서 제거해야 한다.
                    · 입력: 사용자 ID
                    · 처리: DB 조회 후 계정 삭제
                    · 출력: 삭제 성공 여부
                    · 예외: 해당 ID가 존재하지 않을 경우 오류 반환
                </func2>
            </output>

            이제 파일 목록을 분석한 후, 위 형식에 맞춰 출력만 하세요.
            """
            code_interpreter_prompt = PromptTemplate.from_template(code_interpreter_template)
            code_interpreter_result_chain = code_interpreter_prompt | llm | StrOutputParser()
            result = code_interpreter_result_chain.invoke({"information": file_code})
            print("===================================================================================================================")
            print("===================================================================================================================")
            print(" ** result : ", result)

            import re
            func_blocks = re.findall(r"<func\d+>.*?</func\d+>", result, re.DOTALL)

            print(func_blocks)

            def strip_tags(x): 
                return re.sub(r"<.*?>", " ", x, flags=re.DOTALL).strip()

            corpus = [strip_tags(b) for b in func_blocks] # corpus 가 코드 담은 리스트.
            for code in corpus:
                tmpResult = retriever.invoke(code)


            # # 파일 전체 -> 특징점 추출.
            # feats = extract_features(file_path=file_path, full_text=file_code)
            # print("===================================================================================================================")
            # print("===================================================================================================================")
            # print(" ** feats : ", feats)

            # # 특징 기반으로 요약 질의 생성
            # feature_query = build_query_from_features(feats)
            # print(" ** feature_query (LLM 자연어):\n", feature_query)
            # print("===================================================================================================================")
            # print("===================================================================================================================")
            # print(" ** feature_query : ", feature_query)

            # # RAG 검색
            # candidates = search_requirements(vector_store, feature_query, k=5)
            # print("===================================================================================================================")
            # print("===================================================================================================================")
            # print(" ** candidates : ", candidates)

        return commitResult # TODO: 편의상 리턴한거고 확정아님
    
    except KeyError as e:
        print(f"Webhook payload에서 필요한 키를 찾을 수 없습니다: {e}")
        return {"status": "error", "message": f"Missing key in webhook payload: {e}"}
    except Exception as e:
        print(f"Webhook 처리 중 오류 발생: {e}")
        return {"status": "error", "message": str(e)}
    

if __name__ == "__main__":
    # Uvicorn을 사용하여 FastAPI 애플리케이션 실행
   uvicorn.run(app, host="0.0.0.0", port=8000)
   