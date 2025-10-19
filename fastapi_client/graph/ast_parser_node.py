import re
from typing import List

from parser.parser import MethodInfo, FileParseResult, extract_java_methods, extract_python_methods, \
    RegroupMethodResult, extract_java_filename, extract_java_path, analyze_import_java_code
from .state import AgentState


def parse_methods_from_file(state: AgentState) -> List[FileParseResult]:
    file_code_list = state['file_code']
    result_list: List[FileParseResult] = []
    import_class_list = {}
    for file_obj in file_code_list:
        file_name = file_obj['file_name']
        code = file_obj['code']

        if not code:
            continue
        
        parsed_methods: List[MethodInfo] = []
        if file_name.endswith('.py'):
            parsed_methods = extract_python_methods(code)
        
        elif file_name.endswith('.java'):
            parsed_methods:List = extract_java_methods(code)
            import_class_of_methods = analyze_import_java_code(code)
            method_level_analysis:dict = import_class_of_methods['method_level_analysis']
            if method_level_analysis.keys():
                import_class_list = import_class_list|method_level_analysis
            for parsed_method in parsed_methods:
                import_class = method_level_analysis.get(parsed_method.get('method_name'), None)
                if import_class:
                    parsed_method['import_class'] = import_class
                else :
                    parsed_method['import_class'] = None
        else:
            print(f"지원하지 않는 파일 확장자입니다: {file_name}")

        result_list.append({
            "file_name": file_name,
            "method_list": parsed_methods,
        })

    return { "parsed_methods" : result_list, "import_class_of_methods": import_class_list }

def regroup_methods(state: AgentState) -> List[RegroupMethodResult]:
    parsed_methods_list = state['parsed_methods']
    tmp_rfp_number = state['tmp_rfp_number']
    fileCode_list = state['file_code']
    import_class_of_methods:dict = state['import_class_of_methods']
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
            isNeeded = False
            if tmp_rfp_number not in rfp_number:
                for import_class_of_method in import_class_of_methods.values():
                    for usage_list in import_class_of_method.values():
                        for usage in usage_list:
                            if method['method_name'] in usage :
                                isNeeded = True
                        if isNeeded:
                            break
                    if isNeeded:
                        break
                if not isNeeded:
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
                "method_code": method["method_code"],
                "import_class": method["import_class"]
            }


            if file_item:
                file_item["method_list"].append(method_item)
            else:
                rfp_dict[rfp_number]["file_list"].append({
                    "path_name": path_name,
                    "file_name": java_file,
                    "method_list": [method_item]
                })

    for rfp_dict_value in rfp_dict.values():
        result_list.append(rfp_dict_value)

    return {'regrouped_methods': result_list}
