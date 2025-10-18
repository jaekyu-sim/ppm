import json
from typing import List

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

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

def _find_key_by_words(d, canonical_key):
    """
    canonical_key를 구성하는 단어들을 모두 포함하는 키를 딕셔너리에서 찾습니다.
    대소문자를 무시하고, 찾은 첫 번째 키를 반환합니다.
    
    예: canonical_key 'file_name'은 'fileName', 'file_names' 등과 매칭됩니다.
    """
    if not isinstance(d, dict):
        return None
        
    constituent_words = [word for word in canonical_key.split('_') if word]
    if not constituent_words:
        return None

    for key in d.keys():
        normalized_key = key.lower()
        if all(word in normalized_key for word in constituent_words):
            return key
            
    return None

def _get_flexible_value(d, canonical_key, default=None):
    """
    구성 단어 매칭을 통해 유연하게 딕셔너리에서 값을 가져옵니다.
    """
    if not isinstance(d, dict):
        return default
        
    if canonical_key in d:
        return d[canonical_key]
        
    flexible_key = _find_key_by_words(d, canonical_key)
    if flexible_key:
        return d[flexible_key]
        
    return default

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

def summarize_method_function(state: AgentState):
    """
    LLM을 호출하여 각 메서드의 요약(summary)을 생성하고,
    LLM의 출력이 불안정하더라도 원본 데이터 구조를 유지하며 안전하게 병합합니다.
    """
    original_parsed_methods = state['parsed_methods']
    summarize_method_chain = method_summarization_prompt | llm | JsonOutputParser()

    # 1. LLM 호출하여 요약 결과 목록 생성
    llm_results = []
    for file_object in original_parsed_methods:
        result = summarize_method_chain.invoke({"information": [file_object]})
        llm_parsed_methods = _get_flexible_value(result, 'parsed_methods')
        if llm_parsed_methods:
            llm_results.extend(llm_parsed_methods)

    # 2. 요약 결과를 빠르게 찾기 위한 조회용 맵 생성 {file_name: {method_name: summary}}
    summary_map = {}
    for llm_file_obj in llm_results:
        file_name = _get_flexible_value(llm_file_obj, 'file_name')
        if not file_name:
            continue

        summary_map.setdefault(file_name, {})
        
        llm_method_list = _get_flexible_value(llm_file_obj, 'method_list')
        if not isinstance(llm_method_list, list):
            continue

        for llm_method_obj in llm_method_list:
            method_name = _get_flexible_value(llm_method_obj, 'method_name')
            summary = _get_flexible_value(llm_method_obj, 'summary')
            if method_name and summary:
                summary_map[file_name][method_name] = summary

    # 3. 원본 데이터에 요약 정보를 안전하게 병합
    for original_file in original_parsed_methods:
        file_name = original_file.get('file_name')
        if not file_name or file_name not in summary_map:
            continue

        for original_method in original_file.get('method_list', []):
            method_name = original_method.get('method_name')
            if not method_name:
                continue
            
            found_summary = summary_map.get(file_name, {}).get(method_name)
            if found_summary:
                original_method['summary'] = found_summary
            else:
                original_method.setdefault('summary', '')

    return {"parsed_methods": original_parsed_methods}


def match_summary_to_requirement(state:AgentState):
    file_list = state['parsed_methods']
    tmp_rfp_id = state['tmp_rfp_number']

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
                # candidates_with_score = vector_store.similarity_search_with_score(summary, k=3)
                candidates_with_score = vector_store.similarity_search_with_score(summary, k=3)
                candidates = [doc for doc, _ in candidates_with_score]
                scored_docs = ollama_bge_rerank(summary, candidates, top_n=1)

                if scored_docs:
                    top_doc, score = scored_docs[0]
                    rfp_number = top_doc.metadata.get('list_name', 'N/A')

                    try:
                        # json.loads를 사용하여 표준 JSON 문자열을 파싱
                        page_content_dict = json.loads(top_doc.page_content)
                        if isinstance(page_content_dict, dict):
                            # '내용' 키가 없을 때를 대비하여 .get() 사용
                            requirement_content = page_content_dict.get('내용', top_doc.page_content)
                        else:
                            requirement_content = top_doc.page_content
                    except (json.JSONDecodeError, TypeError):
                        # JSON 파싱에 실패하면 원본 문자열을 그대로 사용
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

    return {'parsed_methods': file_list}

# 1. 개별 함수 분석 결과를 위한 모델
class FunctionDetail(BaseModel):
    """소프트웨어 기능 명세를 담는 구조"""
    file: str = Field(description="함수가 위치한 파일명 (예: com.example.course.controller.CourseBookmarkController.java)")
    name: str = Field(description="함수의 기능 이름 (예: getUserBookmarkedCoursesPaged)")
    purpose: str = Field(description="해당 기능의 목적/역할을 설명 (예: 현재 사용자의 즐겨찾기 과정 목록을 페이징하여 조회한다.)")
    input: str = Field(description="함수 호출 시 입력 받는 매개변수, 매개변수가 없으면 빈 값 입력 (예: 인증 정보 (Authentication), 페이징 정보 (Pageable))")
    processing: str = Field(description="함수의 주요 처리 로직/단계에 대한 설명 (예: 인증 정보에서 사용자 ID를 추출하고, 북마크 서비스를 통해 페이징된 즐겨찾기 과정 목록을 조회한 후, 응답으로 반환한다.)")
    output: str = Field(description="기능 수행 후 반환되는 결과, 반환이 없으면 빈 값 입력 (예: 즐겨찾기한 과정 페이지 (Page<CourseResponse>))")
    exceptions: str = Field(description="발생 가능한 예외 상황 및 처리 내용 (예: 사용자를 찾을 수 없을 경우 EntityNotFoundException이 발생한다.)")

# 2. 전체 결과를 위한 모델
class CodeAnalysisResult(BaseModel):
    """Code Interpreter의 최종 분석 결과"""
    functions: List[FunctionDetail]


def code_interpreter(state:AgentState):
    regrouped_methods = state['regrouped_methods']
    results = []  # 최종 FunctionDetail 객체 리스트

    # LLM이 CodeAnalysisResult 전체를 반환하도록 설정
    # Pydantic 모델 클래스 자체를 인수로 전달해야 합니다.
    structured_llm_chain = llm.with_structured_output(CodeAnalysisResult)

    # CodeAnalysisResult의 JSON 스키마를 프롬프트에 주입
    json_schema_full = CodeAnalysisResult.schema_json(indent=2)

    # 단일 파일/항목 분석을 위한 프롬프트
    # LLM에게 List[FunctionDetail]이 아닌 CodeAnalysisResult 객체를 요청합니다.
    single_item_prompt = PromptTemplate.from_template(
        """
        당신은 Code Review 전문가입니다. 아래 '분석 대상 항목'은 하나의 파일 정보이며,
        이 파일 안에 포함된 모든 메서드(`method_list`)를 분석하여
        메서드 개수만큼의 FunctionDetail 객체를 "functions" 배열에 담아 **CodeAnalysisResult 객체**를 반환하세요.
        다른 설명 없이 JSON 객체만 출력하세요.

        CodeAnalysisResult 객체 구조:
        {json_schema_full}

        분석 대상 항목:
        {item_information}
        """
    ).partial(json_schema_full=json_schema_full)  # 스키마를 partial로 미리 주입

    # Chain은 'single_item_prompt'와 'structured_llm_chain'을 연결
    code_interpreter_result_chain = single_item_prompt|structured_llm_chain

    # 1. regrouped_methods 구조 순회
    for rfp_block in regrouped_methods:
        rfp_name = rfp_block.get("rfp_name", "N/A")

        # 2. file_list 순회
        for file_data in rfp_block.get('file_list', []):
            file_name = file_data.get("file_name", "N/A")

            # 3. LLM에게 전달할 항목 정보 문자열 생성 (파일 전체 내용)
            # LLM이 파싱 오류 없이 내용을 볼 수 있도록 문자열로 덤프합니다.
            item_info_str = json.dumps(file_data, indent=2, ensure_ascii=False)

            print(f"** 분석 시작: RFP={rfp_name}, 파일={file_name} **")

            # 4. LLM 호출
            try:

                verdict: CodeAnalysisResult = code_interpreter_result_chain.invoke({
                    "item_information": item_info_str
                })

                # 5. 결과 추출 및 통합
                # 결과는 CodeAnalysisResult 객체이므로, functions 리스트만 추출
                if verdict and verdict.functions:
                    results.extend(verdict.functions)
                    print(f"   -> 성공: {len(verdict.functions)}개 메서드 분석 결과 통합.")
                else:
                    print(f"   -> 경고: LLM이 유효한 functions 리스트를 반환하지 않음.")

            except Exception as e:
                # LLM 호출 및 Pydantic 파싱 실패 시 처리
                print(f"   -> 오류: 처리 중 예외 발생: {e}")
                # 오류가 발생한 파일의 정보는 누락되지만, 전체 루프는 중단되지 않습니다.
                # 필요하다면 여기에 오류 정보를 담은 더미 FunctionDetail을 추가할 수 있습니다.

    # 최종적으로 FunctionDetail 객체 리스트를 딕셔너리 형태로 반환
    return {'functions': [res.model_dump() for res in results]}

judge_schema = """
    {{
    "rfp_id": "<문자열: 요구사항 식별용 라벨>",
    "rfp_contents": "<요구사항에 대한 내용(JSON 구조: 
    {{
        "content": "<요구사항 정보의 '내용'에 해당하는 문자열>",
        "reference": "<요구사항 정보의 '구현시참고사항'에 해당하는 문자열>",
    }}>",
    "summary": "<한 줄 평가 요약>",
    "decision": "충족 | 부분충족 | 미충족",
    "scores": {{
        "기능정합성": 0-1 사이 실수,
        "입력정합성": 0-1 사이 실수,
        "처리정합성": 0-1 사이 실수,
        "출력정합성": 0-1 사이 실수,
    }},
    "missing_points": ["<부족/누락된 요구사항 포인트들>"],
    "trace": {{
        "matched_functions": ["<요구사항에 사용된 함수들 정보(JSON 구조:
        {{
            "file": "",
            "name": "",
            "purpose": "",
            "input": "",
            "processing": "",
            "output": "",
            "exceptions": ""
        }}>"]
        }}
    }}
    """

judge_prompt = PromptTemplate.from_template("""
당신은 소프트웨어 요구사항 검증 전문가입니다.

[평가 목적]
- 주어진 \"요구사항\"에 대해 \"함수 수준 기능 명세(자연어 요약)\"를 바탕으로 얼마나 충족하는지 판정하세요.
- 판정 기준: 기능/입력/처리/출력/예외 5가지 관점.
- RFP 요구사항은 불변의 진리이므로 요구사항의 불완전성을 고려하지 않는다.
- 요구사항 외의 사항은 **절대** 검사하지 않는다.

[출력 형식]
반드시 JSON 하나만 출력. 다른 문구 금지.
스키마: {schema}

[평가 지침]
- \"충족\": 핵심 요구를 대부분 충족하며 잔여 리스크가 경미함
- \"부분충족\": 핵심 중 일부가 불명확/누락
- \"미충족\": 핵심 요구를 만족하지 못함
- 점수는 0.0~1.0 (소수 둘째 자리 권장)
- missing_points에는 구체적 부족 항목을 불릿으로 기입
- trace.matched_functions에는 요구사항을 구성하는 함수의 정보를 나열
- RFP 요구사항은 불변의 진리이므로 요구사항의 불완전성을 고려하지 않음

[입력]
- 요구사항 정보: {requirements_data}
- 함수 리스트: {func_text}

""").partial(schema=judge_schema)

def compare_to_rfp(state:AgentState):
    func_blocks = state['functions']
    tmp_rfp_id = state['tmp_rfp_number']
    requirements_from_db = vector_store.search(query=f"하위ID 값에 {tmp_rfp_id}가 포함된 문서를 찾아줘", search_type="similarity", k=100, filter={"source": tmp_rfp_id})

    my_list = []
    for item in requirements_from_db:
        print(item)
        rfp_number = item.metadata.get('list_name','N/A')
        requirement_content = item.page_content
        my_list.append({'rfp_number': rfp_number, 'requirement_content': requirement_content})

    # 1. 각 딕셔너리의 item()을 가져와 정렬된 튜플로 변환합니다.
    #    (딕셔너리의 키 순서가 달라도 동일한 내용이면 같은 튜플이 되도록 하기 위해 sorted()를 사용합니다.)
    tuple_list = [tuple(sorted(d.items())) for d in my_list]

    # 2. 튜플 리스트를 set으로 변환하여 중복을 제거합니다.
    unique_tuples = set(tuple_list)

    # 3. set의 각 튜플을 다시 딕셔너리로 변환하여 리스트를 만듭니다.
    unique_list = [dict(t) for t in unique_tuples]

    requirements_blocks = sorted(unique_list, key=lambda d: d['rfp_number'])

    def judge_one_func(requirements_data, func_text, llm):

        # 2) LLM 판정
        chain = judge_prompt | llm | JsonOutputParser()
        verdict = chain.invoke({
            "requirements_data": requirements_data,
            "func_text": func_text
        })

        data = verdict

        # 3) 총점 산출(가중 평균 예시)
        weights = {
            "기능정합성": 0.5, "입력정합성": 0.15, "처리정합성": 0.2,
            "출력정합성": 0.15,
        }
        s = data.get("scores", {})
        total = (
            s.get("기능정합성", 0)*weights["기능정합성"] +
            s.get("입력정합성", 0)*weights["입력정합성"] +
            s.get("처리정합성", 0)*weights["처리정합성"] +
            s.get("출력정합성", 0)*weights["출력정합성"]
        )
        data["total_score"] = round(total, 3)
        return data

    results = []
    func_text = ""
    for idx, func_data in enumerate(func_blocks, 1):
        func_text += f"""
        
        -----
        file: {func_data.get('file', '')}
        name: {func_data.get('name', '')}
        purpose: {func_data.get('purpose', '')}
        input: {func_data.get('input', '')}
        processing: {func_data.get('processing', '')}
        output: {func_data.get('output', '')}
        exceptions: {func_data.get('exceptions', '')}
        -----
        
        """.strip()

    for idx, requirements_data in enumerate(requirements_blocks, 1):
        verdict = judge_one_func(requirements_data, func_text, llm)
        results.append(verdict)

    return {'answer' : results, 'requirements' : requirements_blocks}
