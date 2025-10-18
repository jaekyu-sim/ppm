import re
from typing import List

from parser.parser import MethodInfo, FileParseResult, extract_java_methods, extract_python_methods, \
    RegroupMethodResult, extract_java_filename, extract_java_path
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

def regroup_methods(state: AgentState) -> List[RegroupMethodResult]:
    parsed_methods_list = state['parsed_methods']
    tmp_rfp_number = state['tmp_rfp_number']
    fileCode_list = state['file_code']
    fileCode_dic = {}
    for a in fileCode_list:
        file_name = a['file_name']
        code = a['code']
        fileCode_dic[file_name] = code


    result_list: List[RegroupMethodResult] = []

    rfp_dict = {}

    for file in parsed_methods_list:
        file_name = file['file_name']
        # 경로와 파일명 분리
        java_file = extract_java_filename(file_name)
        # 확장자 빼고 패키지 경로 추출
        path_name = extract_java_path(file_name)

        for method in file['method_list']:
            rfp_number = method['rfp_number']
            if tmp_rfp_number not in rfp_number:
                continue
            if rfp_number not in rfp_dict:
                rfp_dict[rfp_number] = {
                    "rfp_name": rfp_number,
                    "file_list": []
                }
            # 파일 내 이미 file_list에 추가됨을 체크
            file_item = next(
                (f for f in rfp_dict[rfp_number]["file_list"]
                 if f["file_name"] == java_file and f["path_name"] == path_name),
                None
            )
            method_item: MethodInfo = {
                "method_name": method["method_name"],
                "method_code": method["method_code"]
            }


            if file_item:
                file_item["method_list"].append(method_item)
            else:
                caller_variable = []

                # 1. import 구문 추출 (클래스명 ↔ import 경로 mapping)
                import_pattern = re.compile(r'import\s+([a-zA-Z0-9_.]+);')
                imports = import_pattern.findall(fileCode_dic[file_name])

                # 2. mapping: SimpleClassName → FullPath
                import_map = {imp.split('.')[-1]: imp for imp in imports}

                # 3. 클래스 내 'private final [Type] [name];' 추출
                member_pattern = re.compile(r'private\s+final\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+);')
                fields = member_pattern.findall(fileCode_dic[file_name])

                for type_name, var_name in fields:
                    # import에서 찾으면 패키지 포함 경로 사용, 아니면 타입 그대로
                    path = import_map.get(type_name, type_name)
                    caller_variable.append({"path": path, "name": var_name})

                rfp_dict[rfp_number]["file_list"].append({
                    "path_name": path_name,
                    "file_name": java_file,
                    "method_list": [method_item],
                    "caller_variable": caller_variable
                })

    for rfp_dict_value in rfp_dict.values():
        result_list.append(rfp_dict_value)

    return {'regrouped_methods': result_list}
