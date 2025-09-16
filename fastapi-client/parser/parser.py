import ast
import re
from typing import List, Dict, TypedDict
import javalang

# TODO : tree-sitter 도입 검토

class MethodInfo(TypedDict):
    method_name: str
    method_code: str

class FileParseResult(TypedDict):
    file_name: str
    method_list: List[MethodInfo]

class VariableInfo(TypedDict):
    path: str
    name: str

class FileInfo(TypedDict):
    path_name: str
    file_name: str
    method_list: List[MethodInfo]
    caller_variable: List[VariableInfo]

class RegroupMethodResult(TypedDict):
    rfp_name: str
    file_list: List[FileInfo]

def extract_python_methods(code: str) -> List[MethodInfo]:
    """
    주어진 파이썬 코드 문자열에서 모든 함수와 메서드를 추출합니다.

    Args:
        code: 파싱할 파이썬 소스 코드입니다.

    Returns:
        메서드 이름과 코드를 포함하는 딕셔너리의 리스트입니다.
    """
    methods: List[MethodInfo] = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_code = ast.get_source_segment(code, node)
                if method_code:
                    methods.append({
                        "method_name": node.name,
                        "method_code": method_code
                    })
    except SyntaxError as e:
        print(f"Python 코드 파싱 중 오류 발생: {e}")
    return methods

def extract_java_methods(java_code: str) -> List[MethodInfo]:
    """
    Java 소스 코드를 파싱하여 모든 메서드의 이름과
    해당 메서드의 주석, 어노테이션을 포함한 원본 코드를 추출합니다.
    (주의: javalang 파싱 실패 시 정규식 기반의 폴백 로직으로 동작)

    Args:
        java_code (str): 파싱할 Java 코드 전체 내용

    Returns:
        메서드 이름과 코드를 포함하는 딕셔너리의 리스트입니다.
    """
    methods: List[MethodInfo] = []
    try:
        # 1. javalang으로 먼저 파싱 시도 (가장 정확함)
        tree = javalang.parse.parse(java_code)
        code_lines = java_code.splitlines()

        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            method_name = node.name
            start_line = node.position.line
            
            if node.annotations:
                first_annotation_line = min(anno.position.line for anno in node.annotations)
                start_line = min(start_line, first_annotation_line)

            doc_start_line_idx = start_line - 1
            while doc_start_line_idx > 0:
                prev_line_idx = doc_start_line_idx - 1
                line_content = code_lines[prev_line_idx].strip()
                if line_content == "" or line_content.startswith(('//', '/*', '*', '*/')):
                    doc_start_line_idx = prev_line_idx
                else:
                    break
            
            method_code_lines = []
            brace_count = 0
            found_start_brace = False
            current_line_idx = doc_start_line_idx
            
            while current_line_idx < len(code_lines):
                line = code_lines[current_line_idx]
                method_code_lines.append(line)

                # 문자열 안의 중괄호는 무시 (간단한 형태만 처리)
                line_outside_strings = re.sub(r'"[^"]*"', '', line)

                if '{' in line_outside_strings:
                    # 메서드 시그니처 라인 이후의 첫번째 중괄호를 본문으로 간주
                    if not found_start_brace and current_line_idx >= start_line - 1:
                        found_start_brace = True
                    
                    if found_start_brace:
                        brace_count += line_outside_strings.count('{')
                
                if '}' in line_outside_strings and found_start_brace:
                    brace_count -= line_outside_strings.count('}')

                if found_start_brace and brace_count == 0:
                    break
                
                if not found_start_brace and line.strip().endswith(';') and current_line_idx >= start_line - 1:
                    break
                
                current_line_idx += 1

            methods.append({
                "method_name": method_name,
                "method_code": "\n".join(method_code_lines)
            })
        
        return methods

    except (javalang.tokenizer.LexerError, javalang.parser.JavaSyntaxError) as e:
        # 2. javalang 파싱 실패 시, 정규식으로 폴백
        print(f"javalang parsing failed: {e}. Falling back to regex-based extraction.")
        
        # 메서드 시그니처를 찾는 정규식 (간략화 버전)
        method_pattern = re.compile(
            r"((?:^\s*(?:@[\w\.]+(?:\(.*\))?|/\*.*?\*/|//.*?)\s*\n)*)"  # Annotations and comments
            r"^\s*(?:public|protected|private|static|[\w\.<>\[\]\s,]+)+\s+"  # Modifiers and return type
            r"([\w]+)\s*"  # Method name
            r"\([^)]*\)\s*(?:throws\s+[\w\s,]+)?\s*\{",  # Parameters and throws
            re.MULTILINE | re.DOTALL
        )
        
        code_lines = java_code.splitlines()
        
        for match in method_pattern.finditer(java_code):
            preamble, method_name = match.groups()
            start_pos = match.start()
            
            start_line_idx = java_code.count('\n', 0, start_pos)
            
            brace_count = 1 # 시작 중괄호는 이미 찾았으므로 1에서 시작
            method_lines = [match.group(0)] # 매치된 전체 시그니처 라인 포함
            
            current_line_idx = java_code.count('\n', 0, match.end())

            for i in range(current_line_idx, len(code_lines)):
                line = code_lines[i]
                method_lines.append(line)
                
                line_outside_strings = re.sub(r'"[^"]*"', '', line)

                brace_count += line_outside_strings.count('{')
                brace_count -= line_outside_strings.count('}')
                
                if brace_count == 0:
                    break
            
            methods.append({
                "method_name": method_name,
                "method_code": "\n".join(method_lines).strip()
            })
            
        return methods

def extract_java_filename(file_path: str) -> str:
    return file_path.split('/')[-1]

def extract_java_path(file_path: str) -> str:
    # 패키지 경로 추출
    # 'src/main/java/' 이후 경로를 사용하여 '.' 으로 연결
    java_root = 'src/main/java/'
    idx = file_path.find(java_root)
    package_path = file_path[idx + len(java_root):-len('.java')] if idx != -1 else ''
    package_parts = package_path.split('/')
    class_name = package_parts[-1]
    package_name = '.'.join(package_parts[:-1] + [class_name])
    return package_name