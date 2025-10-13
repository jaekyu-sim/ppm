import ast
from datetime import datetime

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama

# from rag_boot import load_or_build_vector_store
from rag_boot_phase2 import load_or_build_vector_store
from .state import AgentState

vector_store, _embeddings = load_or_build_vector_store()
# 원래는 아래 한줄.
#retriever = vector_store.as_retriever(search_kwargs={'k': 3})

# rerank 적용하면 아래 내용.
# 초기 후보 많이
base_retriever = vector_store.as_retriever(search_kwargs={'k': 3})

from reranker_ollama import OllamaBGERerankRetriever, ollama_bge_rerank
retriever = OllamaBGERerankRetriever(base_retriever=base_retriever, k_init=3, k_final=2)

llm = ChatOllama(model="qwen3:4b-instruct-2507-q8_0", temperature=0.2, format="json")


method_summarization_prompt = PromptTemplate.from_template(
    """당신은 코드의 핵심 기능을 요구사항 관점에서 간결하게 요약하는 전문 SE(Software Engineer)입니다.

    **임무:**
    주어진 JSON 배열에 포함된 모든 메서드 객체에 대해, 해당 메서드의 핵심 기능을 설명하는 `summary` 필드를 한국어로 추가해 주세요.

    **규칙:**
    1. 입력은 `file_name`, `method_name`, `method_code`를 포함하는 JSON 객체들의 배열입니다.
    2. 출력은 입력 배열과 **동일한 순서와 개수**를 가지며, 각 객체에 `summary` 필드만 추가된 JSON 이어야 합니다.
    3. `summary`는 반드시 **상세 요구사항과 매칭될 것을 고려**하여, 메서드의 기술적 구현 방식보다는 **비즈니스 로직과 목적**이 명확히 드러나도록 작성해야 합니다. (예: "DB에서 데이터를 가져온다" (X) -> "사용자의 프로필 정보를 조회한다" (O))
    4. 응답은 오직 JSON 이어야 하며, 다른 어떤 설명도 포함해서는 안 됩니다.

    **코드 정보:**
    {information}
    
    이제 위의 `코드 정보`를 분석하여, 위의 규칙과 예시를 반드시 준수하는 **JSON 배열**을 생성하세요.

    **JSON 배열 출력 예시 :**
    {{ "parsed_methods": [
        {{
            "file_name": "OrderController.java",
            "method_list": [
                {{
                    "method_name": "getOrder",
                    "method_code": "public Order getOrder(Long orderId) {{ ...  ",
                    "summary": "주문 ID를 받아 특정 주문 내역을 조회하는 API 엔드포인트를 제공합니다."
                }},
                {{ ... }}            
            ]
        }},
        {{
            "file_name": "AuthService.java",
            "method_list": [
                {{
                    "method_name": "login",
                    "method_code": "public TokenResponse login(String username, String password) {{ ...  ",
                    "summary": "사용자 아이디와 비밀번호로 로그인을 수행하고 인증 토큰을 발급합니다."
                }},
                {{ ... }}            
            ]
        }}
    ]
    }}
    """
)

def summarize_method_function(state:AgentState):
    parsed_methods = state['parsed_methods']

    summarize_method_chain = method_summarization_prompt | llm | JsonOutputParser()

    all_summaries = []
    for file_object in parsed_methods:
        start = datetime.now()
        print(f"[{start}] {file_object['file_name']} 에 대한 summarize 작업 시작")
        result = summarize_method_chain.invoke({"information": [file_object]})
        end = datetime.now()
        if result and result.get("parsed_methods"):
            all_summaries.extend(result.get("parsed_methods"))
            print(f"[{end}] 결과에 반영 완료")
        diff = end-start
        print(f"[{end}] {file_object['file_name']} 에 대한 summarize 작업 종료 (걸린시간: {diff.seconds}s)")

    return {"parsed_methods": all_summaries}


def match_summary_to_requirement(state:AgentState):

    file_list = state['parsed_methods']

    print("--- " + "- " * 10 + "4단계: 요약문을 RAG에 검색하여 요구사항 매칭 시작" + "- " * 10 + " ---")

    for file_object in file_list:
        for method in file_object.get('method_list', []):
            summary = method.get('summary')
            rfp_number = 'N/A'
            requirement_content = 'N/A'
            score = 0.0
            
            if summary:
                # rerank 포인트2
                # 아래 한줄 주석.
                #scored_docs = vector_store.similarity_search_with_score(summary, k=3)

                # 아래 추가.
                candidates_with_score = vector_store.similarity_search_with_score(summary, k=3)
                candidates = [doc for doc, _ in candidates_with_score]
                scored_docs = ollama_bge_rerank(summary, candidates, top_n=1)
                
                if scored_docs:
                    top_doc, score = scored_docs[0]
                    rfp_number = top_doc.metadata.get('list_name', 'N/A')
                    
                    try:
                        # ast.literal_eval을 사용하여 문자열을 안전하게 Python 객체로 변환
                        page_content_dict = ast.literal_eval(top_doc.page_content)
                        if isinstance(page_content_dict, dict):
                            requirement_content = page_content_dict.get('내용', 'Content key not found')
                        else:
                            requirement_content = top_doc.page_content
                    except (ValueError, SyntaxError):
                        # 파싱에 실패하면 원본 문자열을 그대로 사용
                        requirement_content = top_doc.page_content
            
            method['rfp_number'] = rfp_number
            method['score'] = score
            method['requirement_content'] = requirement_content

            print(
                f"[File: {file_object['file_name']}]\n"
                f"  - Method: {method['method_name']}\n"
                f"  - Summary: {summary or 'No summary available'}\n"
                f"  => Matched RFP: {rfp_number} (Score: {score:.4f})\n"
                f"     ㄴ 내용: {requirement_content}\n"
                f"--------------------------------------------------"
            )
            
    print("--- " + "- " * 10 + "4단계: 요구사항 매칭 완료" + "- " * 10 + " ---")

    return { 'parsed_methods' : file_list }

code_interpreter_prompt = PromptTemplate.from_template(
    """
    당신은 Code Review 전문가이며, 아래의 `information List`에 포함된 모든 항목(each item)을 분석해야 합니다.
    각 항목마다 하나의 객체를 만들어 JSON 배열에 추가하세요.
    어떤 항목도 생략하지 마세요.

    결과는 아래 JSON 스키마를 따르며, "functions" 배열 안에 각 항목의 분석 결과를 모두 포함해야 합니다.
    다른 설명 없이 JSON만 출력하세요.
    ```json
    {{
        "functions": [
            {{
                "file": "파일A 명",
                "name": "사용자 등록 기능",
                "purpose": "신규 사용자의 정보를 받아 시스템에 계정을 생성해야 한다.",
                "input": "사용자 이름, 이메일, 비밀번호",
                "processing": "이메일 중복 여부 검사 → 비밀번호 암호화 → DB 저장",
                "output": "등록 성공 시 사용자 ID 반환",
                "exceptions": "이메일 중복 시 오류 메시지 반환"
            }},
            {{
                "file": "파일B 명",
                "name": "사용자 삭제 기능",
                "purpose": "특정 사용자의 계정을 시스템에서 제거해야 한다.",
                "input": "사용자 ID",
                "processing": "DB 조회 후 계정 삭제,
                "output": "삭제 성공 여부",
                "exceptions": "해당 ID가 존재하지 않을 경우 오류 반환"
            }}
        ]
    }}```

    이제 다음 제공된 'information List'를 분석하고, 위의 JSON 형식을 **반드시** 준수하여 결과물을 생성하세요. 다른 말은 절대 추가하지 마세요.
    information List:
    {information}
    """
)


def code_interpreter(state:AgentState):
    regrouped_methods = state['regrouped_methods']
    code_interpreter_result_chain = code_interpreter_prompt | llm | JsonOutputParser()
    result = code_interpreter_result_chain.invoke({"information": regrouped_methods})

    return {'answer': result}


judge_schema = """
    {{
    "function_name": "<문자열: 함수 식별용 라벨(없으면 파일명+인덱스)>",
    "summary": "<한 줄 평가 요약>",
    "decision": "충족 | 부분충족 | 미충족",
    "scores": {{
        "기능정합성": 0-1 사이 실수,
        "입력정합성": 0-1 사이 실수,
        "처리정합성": 0-1 사이 실수,
        "출력정합성": 0-1 사이 실수,
        "예외정합성": 0-1 사이 실수,
        "코드위험성": 0-1 사이 실수,
    }},
    "missing_points": ["<부족/누락된 요구사항 포인트들>"],
    "trace": {{
        "matched_requirement_ids": ["<선정된 요구사항 id 또는 출처>"]
    }}
    """

judge_prompt = PromptTemplate.from_template("""
당신은 소프트웨어 요구사항 검증 전문가입니다.

[평가 목적]
- 주어진 \"함수 수준 기능 명세(자연어 요약)\"가 아래 \"요구사항 후보들\"을 얼마나 충족하는지 판정하세요.
- 판정 기준: 기능/입력/처리/출력/예외 5가지 관점.

[출력 형식]
반드시 JSON 하나만 출력. 다른 문구 금지.
스키마: {schema}

[평가 지침]
- \"충족\": 핵심 요구를 대부분 충족하며 잔여 리스크가 경미함
- \"부분충족\": 핵심 중 일부가 불명확/누락
- \"미충족\": 핵심 요구를 만족하지 못함
- 점수는 0.0~1.0 (소수 둘째 자리 권장)
- missing_points에는 구체적 부족 항목을 불릿으로 기입
- trace.matched_requirement_ids에는 근거가 된 요구사항의 id나 출처를 나열

[입력]
- 함수명/식별자: {func_label}
- 함수 명세(자연어): {func_text}
- 요구사항 후보들(Top-{k}): {requirements_block}
""").partial(schema=judge_schema, k=1)

def compare_to_rfp(state:AgentState):
    result_data = state['answer']
    func_blocks = result_data.get("functions", [])
    #print(" ** ** ** func_blocks : ", func_blocks)

    def build_requirements_block(docs):
        lines = []
        for i, d in enumerate(docs, 1):
            rid = d.metadata.get("id") or d.metadata.get("source") or f"req_{i}"
            lines.append(f"- [{rid}] {d.page_content.strip()}")
        return "\n".join(lines)

    def judge_one_func(func_label, func_text, retriever, llm):
        # 1-1) 검색
        docs = retriever.invoke(func_text)
        req_block = build_requirements_block(docs)

        # rerank 포인트1

        # 2) LLM 판정
        chain = judge_prompt | llm | JsonOutputParser()
        verdict = chain.invoke({
            "func_label": func_label,
            "func_text": func_text,
            "requirements_block": req_block
        })
        
        data = verdict

        # 3) 총점 산출(가중 평균 예시)
        weights = {
            "기능정합성": 0.3, "입력정합성": 0.15, "처리정합성": 0.2,
            "출력정합성": 0.15, "예외정합성": 0.1, "코드위험성": 0.1
        }
        s = data.get("scores", {})
        total = (
            s.get("기능정합성", 0)*weights["기능정합성"] +
            s.get("입력정합성", 0)*weights["입력정합성"] +
            s.get("처리정합성", 0)*weights["처리정합성"] +
            s.get("출력정합성", 0)*weights["출력정합성"] +
            s.get("예외정합성", 0)*weights["예외정합성"] + 
            s.get("코드위험성", 0)*weights["코드위험성"]
        )
        data["total_score"] = round(total, 3)
        data["requirements_candidates"] = [
            {
                "id": d.metadata.get("id") or d.metadata.get("source"),
                # "#score": getattr(d, "score", None), --> 모든 값이 None 으로 나옴
                "snippet": d.page_content[:300]
            } for d in docs
        ]
        return data
    
    results = []
    for idx, func_data in enumerate(func_blocks, 1):
        func_label = func_data.get("name") or f"func{idx}"

        func_text = f"""
        파일명: {func_data.get('file', '')}
        기능명: {func_data.get('name', '')}
        목적: {func_data.get('purpose', '')}
        입력: {func_data.get('input', '')}
        처리: {func_data.get('processing', '')}
        출력: {func_data.get('output', '')}
        예외: {func_data.get('exceptions', '')}
        """.strip()

        verdict = judge_one_func(func_label, func_text, retriever, llm)
        verdict["raw_block"] = func_data # 원문 보관
        results.append(verdict)
    #print("*** *** *** ", results)

    return {'answer' : results}
