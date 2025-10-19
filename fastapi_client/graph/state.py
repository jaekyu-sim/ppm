from typing_extensions import TypedDict


class AgentState(TypedDict):
    query: str
    context: list
    answer: str
    requirements: list # 요구사항 목록
    file_code: list # 파일별 소스코드 전문 (raw)
    parsed_methods: list # 파일별 메서드 리스트 (AST 파싱 결과)
    import_class_of_methods: list # 메서드 별 import 된 class 정보
    regrouped_methods: list # 멤버변수가 포함된 요구사항별 메서드 리스트
    functions: list # 각각의 메서드에 대한 분석 정보 리스트 (code_interpreter 결과)
    tmp_rfp_number: str # 요구사항 번호 (PR 브랜치명)