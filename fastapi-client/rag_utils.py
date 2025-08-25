from typing import List, Tuple, Dict, Any
from textwrap import dedent
import json

def search_requirements(vector_store, query: str, k: int = 5) -> List[Tuple[Dict, float]]:
    results = vector_store.similarity_search_with_score(query, k=k)
    out = []
    for doc, score in results:
        meta = doc.metadata.copy()
        meta["snippet"] = doc.page_content[:400]
        out.append((meta, float(score)))
    return out

JUDGE_PROMPT = dedent("""
You are a strict software requirements reviewer.

Given:
1) A code file context (file path, summarized features, sampled content).
2) A candidate requirement (id/title/snippet).

Without seeing diffs, decide whether THIS FILE CONTENT suggests the requirement is implemented.

Return strict JSON with:
- status: "Meets" | "Partial" | "Missing" | "Conflict"
- confidence: float between 0 and 1
- evidence: up to 3 bullets (endpoints, method names, SQL tables, config keys)
- notes: brief advice (e.g., add validation, tests, error handling)
- coverage: which acceptance aspects seem satisfied vs missing (if applicable)

Be conservative: If acceptance criteria (validation, error handling, tests) are not clearly present in the file, mark as Partial or Missing.
""").strip()

def build_judge_input(feature_query: str, req_meta: Dict) -> str:
    rid = req_meta.get("req_id") or req_meta.get("source_path","RFP")
    title = req_meta.get("title","")
    snippet = req_meta.get("snippet","")
    return f"""{JUDGE_PROMPT}

=== FILE FEATURE SUMMARY ===
{feature_query}

=== REQUIREMENT ===
[{rid}] {title}
SNIPPET:
{snippet}

Return JSON only.
"""

async def judge_one(llm_call, feature_query: str, req_meta: Dict) -> Dict[str, Any]:
    prompt = build_judge_input(feature_query, req_meta)
    raw = await llm_call(prompt)
    try:
        data = json.loads(raw)
    except Exception:
        data = {
            "status":"Missing","confidence":0.0,
            "evidence":["LLM JSON parse failed"],"notes":raw[:300],"coverage":""
        }
    data["req_id"] = req_meta.get("req_id") or req_meta.get("source_path","RFP")
    data["req_title"] = req_meta.get("title","")
    return data