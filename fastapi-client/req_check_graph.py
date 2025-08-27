# app/graphs/req_check_graph.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, asyncio
from typing import TypedDict, List, Dict, Any, Optional, Tuple

from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.schema import Document

# ====== 상태 정의 ======
class ReqState(TypedDict, total=False):
    file_path: str
    code: str

    # 요약 결과
    spec_json: Dict[str, Any]
    nat_spec: str
    feature_query: str

    # 검색/판정
    candidates: List[Dict[str, Any]]       # [{content, metadata, score}]
    judgments: List[Dict[str, Any]]        # per requirement

# ====== 프롬프트들 ======
SCHEMA = """
{ 
  "file_path": "<문자열>",
  "purpose": "<파일의 역할/목적 한 줄>",
  "endpoints": [{"method":"GET|POST|PUT|DELETE|*", "path":"<경로>", "summary":"<한 줄>"}],
  "inputs": ["<주요 입력 DTO/파라미터/바디 타입>"],
  "outputs": ["<주요 출력 DTO/리턴 타입>"],
  "auth": {"uses_auth": true/false, "mechanism": ["JWT","SecurityContextHolder","Spring Security","None"], "notes":"<있으면>"},
  "validation": {"uses": true/false, "items": ["@Valid","BeanValidation","CustomValidator"]},
  "errors": [{"condition":"<오류상황>", "handling":"<처리 요약>"}],
  "external_calls": ["<Service.method>", "<외부 API 호출명>"],
  "db": {"orm_entities": ["<엔티티/리포지토리명>"], "tables": ["<추정 테이블명(있으면)>"]},
  "side_effects": ["<로그, 파일쓰기, 메시지 발행 등>"],
  "keywords_ko": ["<검색용 핵심 한국어 키워드들>"],
  "natural_spec_ko": "<이 파일의 기능을 한국어로 6~10줄 요약>"
}
""".replace("{","{{").replace("}","}}")  # 전체 이스케이프
CODE_TO_SPEC_PROMPT = f"""당신은 코드 리더입니다. 다음 소스코드가 수행하는 기능을 한국어로 구조화하세요.
반드시 아래 JSON 스키마로만 출력하세요. 설명문/코드블록 금지. JSON 외 텍스트 금지.

스키마:
{
  SCHEMA
}

요구사항:
- 엔드포인트가 없으면 비워둡니다.
- 인증/권한/검증/예외 처리/서비스 호출은 가능한 한 구체적으로.
- JSON 외 텍스트/주석/백틱 금지.

[파일경로]
{{file_path}}

[소스코드]
{{code}}
"""

JUDGE_PROMPT = """You are a strict software requirements reviewer.

Given:
1) The NATURAL SPEC of a code file (Korean).
2) A candidate requirement chunk from the RFP.

Without diff, decide whether the file CONTENT SUGGESTS the requirement is implemented.

Return strict JSON with:
- status: "Meets" | "Partial" | "Missing" | "Conflict"
- confidence: float (0~1)
- evidence: up to 3 bullets referencing endpoints/DTOs/auth/validation/service calls seen
- notes: brief advice or risk
- coverage: which acceptance aspects seem satisfied vs missing (if applicable)
"""

# ====== 유틸 ======
def _strip_code_fences(s: str) -> str:
    return re.sub(r"^```.*?\n|\n```$", "", s.strip(), flags=re.DOTALL)

def _coerce_json(text: str) -> Dict[str, Any]:
    t = _strip_code_fences(text)
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON found")
    chunk = re.sub(r",\s*([}\]])", r"\1", m.group(0))      # trailing comma 방지
    return json.loads(chunk)

def _feature_query_from_spec(spec: Dict[str, Any]) -> str:
    eps = spec.get("endpoints") or []
    ep_str = ", ".join([f"{e.get('method','*')} {e.get('path','')}" for e in eps if e.get("path")])
    keywords = ", ".join(spec.get("keywords_ko") or [])
    nat = spec.get("natural_spec_ko") or spec.get("purpose","")
    return (
        f"[FILE] {spec.get('file_path','')}\n"
        f"routes=[{ep_str}]\n"
        f"KEYWORDS=[{keywords}]\n\n"
        f"NATURAL_SPEC:\n{nat}"
    )

# ====== 노드 구현 ======

def make_summarize_node(llm):
    prompt = ChatPromptTemplate.from_template(CODE_TO_SPEC_PROMPT)
    chain = prompt | llm | StrOutputParser()

    async def summarize_code(state: ReqState) -> ReqState:
        raw = await chain.ainvoke({
            "file_path": state["file_path"],
            "code": state["code"][:13000]
        })
        spec = _coerce_json(raw)
        spec.setdefault("file_path", state["file_path"])
        feature_query = _feature_query_from_spec(spec)
        nat_spec = spec.get("natural_spec_ko") or spec.get("purpose","")
        return {
            **state,
            "spec_json": spec,
            "nat_spec": nat_spec,
            "feature_query": feature_query
        }
    return summarize_code

def make_retrieve_node(vector_store, top_k: int = 5):
    async def retrieve_requirements(state: ReqState) -> ReqState:
        q = state["feature_query"]
        results: List[Tuple[Document, float]] = vector_store.similarity_search_with_score(q, k=top_k)
        cands = []
        for doc, score in results:
            cands.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": float(score)
            })
        return {**state, "candidates": cands}
    return retrieve_requirements

def make_judge_node(llm):
    judge_prompt = ChatPromptTemplate.from_messages([
        ("system", JUDGE_PROMPT),
        ("human", "=== NATURAL SPEC (KO) ===\n{nat}\n\n=== REQUIREMENT CHUNK ===\n{req}\n\nReturn JSON only.")
    ])
    chain = judge_prompt | llm | StrOutputParser()

    async def _judge_one(nat: str, req_chunk: str) -> Dict[str, Any]:
        raw = await chain.ainvoke({"nat": nat[:4000], "req": req_chunk[:4000]})
        try:
            data = _coerce_json(raw)
        except Exception:
            data = {"status":"Missing","confidence":0.0,
                    "evidence":["LLM JSON parse failed"],"notes": raw[:300], "coverage":""}
        return data

    async def judge_alignment(state: ReqState) -> ReqState:
        nat = state["nat_spec"]
        cands = state.get("candidates", [])[:5]
        tasks = []
        for c in cands:
            req_text = c["content"]
            tasks.append(_judge_one(nat, req_text))
        judgs = await asyncio.gather(*tasks)

        # 후보 메타 병합
        out = []
        for j, c in zip(judgs, cands):
            j["req_meta"] = c.get("metadata", {})
            j["retrieval_score"] = c.get("score", None)
            out.append(j)

        return {**state, "judgments": out}
    return judge_alignment

# ====== 그래프 생성기 ======
def create_req_check_graph(vector_store, llm, top_k: int = 5):
    g = StateGraph(ReqState)
    g.add_node("summarize_code", make_summarize_node(llm))
    g.add_node("retrieve_requirements", make_retrieve_node(vector_store, top_k))
    g.add_node("judge_alignment", make_judge_node(llm))

    g.add_edge(START, "summarize_code")
    g.add_edge("summarize_code", "retrieve_requirements")
    g.add_edge("retrieve_requirements", "judge_alignment")
    g.add_edge("judge_alignment", END)
    return g.compile()
