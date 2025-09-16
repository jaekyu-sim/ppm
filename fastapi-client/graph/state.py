from typing_extensions import TypedDict


class AgentState(TypedDict):
    query: str
    context: list
    answer: str
    file_code: list # 파일별 소스코드 전문 (raw)
    parsed_methods: list # 파일별 메서드 리스트 (AST 파싱 결과)
    regrouped_methods: list # 멤버변수가 포함된 요구사항별 메서드 리스트