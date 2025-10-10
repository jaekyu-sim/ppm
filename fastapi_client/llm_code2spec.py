# llm_code2spec.py
# -*- coding: utf-8 -*-
import json, re, asyncio, hashlib
from typing import Dict, Any, Optional, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 모델이 JSON만 내놓도록 강하게 유도 (한국어)
CODE_TO_SPEC_PROMPT = """당신은 코드 리더입니다. 다음 소스코드가 수행하는 기능을 한국어로 구조화하세요.
반드시 아래 JSON 스키마로만 출력하세요. 설명문/코드블록 금지. JSON 외 텍스트 금지.

스키마:
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

요구사항:
- 엔드포인트가 없으면 비워둡니다.
- 인증/권한/검증/예외 처리/서비스 호출은 가능한 한 구체적으로 기입합니다.
- Spring/Security/JWT/DTO 명칭을 정확히 적으세요.
- JSON 외 텍스트/주석/백틱 금지.

[파일경로]
{file_path}

[소스코드]
{code}
"""

def _strip_code_fences(s: str) -> str:
    return re.sub(r"^```.*?\n|\n```$", "", s.strip(), flags=re.DOTALL)

def _coerce_json(text: str) -> Dict[str, Any]:
    """모델 출력에서 JSON만 뽑고 사소한 오류를 보정."""
    t = _strip_code_fences(text)
    m = re.search(r"\{.*\}", t, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in model output")
    chunk = m.group(0)
    # 흔한 오류: 후행 콤마 제거
    chunk = re.sub(r",\s*([}\]])", r"\1", chunk)
    return json.loads(chunk)

async def code_to_spec_json(llm, file_path: str, code: str, max_chars: int = 13000) -> Dict[str, Any]:
    """코드를 LLM으로 분석 → JSON 스펙 반환."""
    prompt = ChatPromptTemplate.from_template(CODE_TO_SPEC_PROMPT)
    chain = prompt | llm | StrOutputParser()
    raw = await chain.ainvoke({"file_path": file_path, "code": code[:max_chars]})
    spec = _coerce_json(raw)
    spec.setdefault("file_path", file_path)
    return spec

def feature_query_from_spec(spec: Dict[str, Any]) -> str:
    """RAG 검색용 feature_query 문자열 생성."""
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

# (선택) 간단 캐시: 동일 내용 파일 재요약 방지
_CODE_SUMMARY_CACHE: Dict[str, Dict[str,Any]] = {}

def _hash_code(file_path: str, code: str) -> str:
    return hashlib.sha256((file_path + "\n" + code).encode("utf-8")).hexdigest()

async def build_feature_query_with_llm(llm, file_path: str, code: str) -> str:
    key = _hash_code(file_path, code)
    if key in _CODE_SUMMARY_CACHE:
        spec = _CODE_SUMMARY_CACHE[key]
    else:
        spec = await code_to_spec_json(llm, file_path, code)
        _CODE_SUMMARY_CACHE[key] = spec
    return feature_query_from_spec(spec)