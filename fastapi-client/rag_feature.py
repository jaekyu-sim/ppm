import re
from typing import Dict

ROUTE_PATTERNS = [
    r'@GetMapping\("([^"]+)"\)', r'@PostMapping\("([^"]+)"\)', r'@PutMapping\("([^"]+)"\)',
    r'@DeleteMapping\("([^"]+)"\)', r'@RequestMapping\("([^"]+)"\)',
    r'@app\.get\([\'"]([^\'"]+)[\'"]\)', r'@app\.post\([\'"]([^\'"]+)[\'"]\)',
    r'app\.get\([\'"]([^\'"]+)[\'"]\)', r'app\.post\([\'"]([^\'"]+)[\'"]\)',
    r'FastAPI\(', r'APIRouter\(', r'@router\.(get|post|put|delete)\([\'"]([^\'"]+)[\'"]\)',
]

#SQL_PATTERNS = [
#    r'\bSELECT\b.+?\bFROM\b\s+([a-zA-Z0-9_\.]+)',
#    r'\bINSERT\s+INTO\b\s+([a-zA-Z0-9_\.]+)',
#    r'\bUPDATE\b\s+([a-zA-Z0-9_\.]+)',
#    r'\bDELETE\s+FROM\b\s+([a-zA-Z0-9_\.]+)'
#]

CLASS_FUNC_PATTERNS = [
    r'\bclass\s+([A-Za-z_][A-Za-z0-9_]*)',       # Python/Java class
    r'\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\(',       # Python def
    r'\bpublic\s+[A-Za-z<>\[\]]+\s+([a-zA-Z_][A-Za-z0-9_]*)\(',  # Java method
]

CONFIG_PATTERNS = [
    r'\bENV[_A-Z0-9]+\b', r'\b[A-Z0-9_]{3,}\b=.*', r'"[A-Za-z0-9_]+" *: *("[^"]+"|\d+|true|false|null)'
]

def _findall(patterns, text):
    found = []
    for p in patterns:
        for m in re.findall(p, text, flags=re.IGNORECASE|re.MULTILINE|re.DOTALL):
            if isinstance(m, tuple):
                found.append("/".join([str(x) for x in m if x]))
            else:
                found.append(str(m))
    return list(dict.fromkeys(found))[:50]  # 중복 제거 후 50개까지

def extract_features(file_path: str, full_text: str) -> Dict:
    # 너무 긴 파일은 앞/중간/끝만 샘플링
    n = len(full_text)
    sample = full_text[:8000] + "\n...\n" + full_text[max(0, n//2-4000):min(n, n//2+4000)] + "\n...\n" + full_text[-8000:]

    routes = _findall(ROUTE_PATTERNS, sample)
    # sql    = _findall(SQL_PATTERNS, sample)
    defs   = _findall(CLASS_FUNC_PATTERNS, sample)
    confs  = _findall(CONFIG_PATTERNS, sample)

    # 간단한 파일 역할 감지 힌트
    is_controller = any(x for x in routes) or ("Controller" in file_path or "router" in file_path.lower())
    is_repo = ("Repository" in file_path or "repo" in file_path.lower())
    is_service = ("Service" in file_path or "service" in file_path.lower())

    return {
        "file_path": file_path,
        "routes": routes,
        # "sql_tables": sql,
        "defs": defs,
        "configs": confs,
        "hints": {
            "is_controller": is_controller,
            "is_repository": is_repo,
            "is_service": is_service
        },
        "sampled": sample[:4000]  # 질의에 쓸 짧은 컨텍스트
    }

def build_query_from_features(feat: Dict) -> str:
    # 벡터 검색에 쓸 짧은 요약 질의(= diff 대체재)
    head = f"[FILE] {feat['file_path']}"
    roles = []
    for k, v in feat["hints"].items():
        if v: roles.append(k.replace("is_", ""))

    routes = ", ".join(feat["routes"][:10]) if feat["routes"] else ""
    # tables = ", ".join(feat["sql_tables"][:10]) if feat["sql_tables"] else ""
    defs   = ", ".join(feat["defs"][:10]) if feat["defs"] else ""
    confs  = ", ".join(feat["configs"][:10]) if feat["configs"] else ""

    return (
        f"{head}\n"
        f"roles={roles or []}\n"
        f"routes=[{routes}]\n"
        # f"tables=[{tables}]\n"
        f"defs=[{defs}]\n"
        f"configs=[{confs}]\n\n"
        f"SUMMARY_CONTEXT:\n{feat['sampled']}"
    )