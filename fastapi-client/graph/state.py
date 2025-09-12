from typing_extensions import TypedDict
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    query: str
    context: list
    answer: str
    file_code: list # 파일별 소스코드 전문 (raw)
    methods_by_file: list # 파일별 메서드 리스트 (AST 파싱 결과)