
from typing import List, Dict, TypedDict

from parser.parser import MethodInfo, FileParseResult, extract_java_methods, extract_python_methods
from .state import AgentState


def parse_methods_from_file(state: AgentState) -> List[FileParseResult]:
    file_code_list = state['file_code']
    result_list: List[FileParseResult] = []

    for file_obj in file_code_list:
        file_name = file_obj['file_name']
        code = file_obj['code']

        if not code:
            continue
        
        parsed_methods: List[MethodInfo] = []
        if file_name.endswith('.py'):
            parsed_methods = extract_python_methods(code)
        
        elif file_name.endswith('.java'):
            parsed_methods = extract_java_methods(code)
            
        else:
            print(f"지원하지 않는 파일 확장자입니다: {file_name}")

        result_list.append({
            "file_name": file_name,
            "method_list": parsed_methods
        })

    return { "parsed_methods" : result_list }