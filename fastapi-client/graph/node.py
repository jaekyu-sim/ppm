import json
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from rag_boot import load_or_build_vector_store
from .state import AgentState
import re


vector_store, _embeddings = load_or_build_vector_store()
retriever = vector_store.as_retriever(search_kwargs={'k': 3})
llm = ChatOllama(model="qwen3:4b", temperature=0.2, format="json")


code_interpreter_prompt = PromptTemplate.from_template(
    """
    당신은 Code Review 전문가이며, 주어진 JSON 형식에 따라 출력을 생성하는 기계입니다. 다른 어떤 설명도 없이, 오직 요청된 JSON 형식의 결과물만 생성해야 합니다.

    지금부터 제공해주는 코드 파일들의 기능을 함수 단위로 분석하세요.
    단순 요약이 아니라, **해당 함수를 개발하기 위해 정의되었을 법한 '요구사항 정의서 수준의 기능 명세'**로 출력하세요.

    information List : {information}

    아래 JSON 스키마에 맞춰서 결과물을 생성하세요. 모든 값은 한글로 작성해야 합니다.

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

    이제 제공된 'information List'를 분석하고, 위의 JSON 형식을 **반드시** 준수하여 결과물을 생성하세요. 다른 말은 절대 추가하지 마세요.
    """)


def code_interpreter(state:AgentState):
    file_code = state['file_code']
    code_interpreter_result_chain = code_interpreter_prompt | llm | JsonOutputParser()
    result = code_interpreter_result_chain.invoke({"information": file_code})

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
- 주어진 "함수 수준 기능 명세(자연어 요약)"가 아래 "요구사항 후보들"을 얼마나 충족하는지 판정하세요.
- 판정 기준: 기능/입력/처리/출력/예외 5가지 관점.

[출력 형식]
반드시 JSON 하나만 출력. 다른 문구 금지.
스키마: {schema}

[평가 지침]
- "충족": 핵심 요구를 대부분 충족하며 잔여 리스크가 경미함
- "부분충족": 핵심 중 일부가 불명확/누락
- "미충족": 핵심 요구를 만족하지 못함
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
        # 1) 검색
        docs = retriever.invoke(func_text)
        req_block = build_requirements_block(docs)

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
                #"score": getattr(d, "score", None),
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
