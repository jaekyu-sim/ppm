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

def infer_base_package(imports: list[str]) -> str:
    """
    비표준 라이브러리 import 구문들 중에서 가장 긴 공통 접두사를 찾아
    개발자가 정의한 애플리케이션 코드의 루트 패키지를 추론합니다.
    """
    # 흔히 사용되는 외부 또는 표준 라이브러리 접두사 목록
    EXTERNAL_PREFIXES = (
        'java.', 'javax.', 'jakarta.', 'org.springframework.', 'org.hibernate.',
        'org.slf4j.', 'org.apache.', 'lombok.', 'com.google.', 'com.fasterxml.',
        'net.', 'io.', 'sun.', 'jdk.', 'scala.', 'kotlin.'
    )

    # 외부/표준 라이브러리 import를 필터링
    custom_imports = [
        imp.strip() for imp in imports
        if imp.strip().count('.') >= 2 and not imp.strip().startswith(EXTERNAL_PREFIXES)
    ]

    if not custom_imports:
        # 커스텀 import가 없으면 기본값으로 대체
        return 'com.example'

    # Longest Common Prefix (LCP) 찾기
    first_import_parts = custom_imports[0].split('.')
    lcp_parts = []

    for i in range(len(first_import_parts) - 1): # 클래스 이름 자체는 제외
        part = first_import_parts[i]
        is_common = True
        for other_import in custom_imports[1:]:
            other_parts = other_import.split('.')
            if len(other_parts) <= i or other_parts[i] != part:
                is_common = False
                break

        if is_common:
            lcp_parts.append(part)
        else:
            break

    # LCP는 최소 두 부분 이상이어야 합니다 (예: com.example)
    if len(lcp_parts) < 2:
        return '.'.join(first_import_parts[:2]) if len(first_import_parts) >= 2 else 'com.example'

    return '.'.join(lcp_parts)

def analyze_import_java_code(java_code: str) -> dict:
    """
    javalang 라이브러리를 사용하여 Java 코드를 분석하고
    각 메서드 내에서 개발자 클래스 의존성과 호출 메서드를 분류합니다.
    """
    try:
        tree = javalang.parse.parse(java_code)
    except (javalang.tokenizer.LexerError, javalang.parser.ParserError) as e:
        return {"error": f"Java 코드 파싱 오류: {e}"}

    main_class_package = tree.package.name if tree.package else 'unknown.package'
    main_class_name = tree.types[0].name if tree.types else 'UnknownClass'
    main_class_full_path = f"{main_class_package}.{main_class_name}"

    all_imports = [imp.path for imp in tree.imports]
    BASE_PACKAGE = infer_base_package(all_imports)

    custom_classes = {} # Simple Name -> Full Path
    for imp in tree.imports:
        if imp.path.startswith(BASE_PACKAGE) and imp.path.count('.') >= 2:
            simple_class_name = imp.path.split('.')[-1]
            custom_classes[simple_class_name] = imp.path

    method_analysis_results = {}

    class_body = tree.types[0].body if tree.types else []

    # Iterate through each method declaration
    for method_decl in (n for n in class_body if isinstance(n, javalang.tree.MethodDeclaration)):
        method_name = method_decl.name
        method_calls = {full_path: set() for full_path in custom_classes.values()} # Track calls per method
        actively_used_candidates = {} # FullPath -> Set[UsageType] per method
        type_only_classes = set() # FullPath per method

        # Traverse the method's subtree
        for path, node in method_decl.filter(javalang.tree.Node):

            # A. Method Invocation
            if isinstance(node, javalang.tree.MethodInvocation):
                qualifier = getattr(node, 'qualifier', None)
                # Check if the qualifier is a custom class or a field of a custom class
                if qualifier in custom_classes:
                    full_path = custom_classes[qualifier]
                    method_calls[full_path].add(f"{node.member}")
                # Heuristic: Check if the qualifier is a field name that maps to a custom class
                elif qualifier in [d.name for fd in class_body if isinstance(fd, javalang.tree.FieldDeclaration) for d in fd.declarators if isinstance(fd.type.name, str) and fd.type.name in custom_classes]:
                     field_declarations = [fd for fd in class_body if isinstance(fd, javalang.tree.FieldDeclaration)]
                     for fd in field_declarations:
                         for declarator in fd.declarators:
                              if declarator.name == qualifier and fd.type.name in custom_classes:
                                  full_path = custom_classes[fd.type.name]
                                  method_calls[full_path].add(f"{node.member}")


            # B. Constructor Invocation
            elif isinstance(node, javalang.tree.ClassCreator):
                if node.type.name in custom_classes:
                    full_path = custom_classes[node.type.name]
                    if full_path not in actively_used_candidates: actively_used_candidates[full_path] = set()
                    actively_used_candidates[full_path].add("new()")

            # C. Member Reference
            elif isinstance(node, javalang.tree.MemberReference):
                if node.qualifier in custom_classes:
                    full_path = custom_classes[node.qualifier]
                    if full_path not in actively_used_candidates: actively_used_candidates[full_path] = set()
                    actively_used_candidates[full_path].add(f"::{node.member}")

            # D. Type Usage (Method parameters, return types, variable declarations)
            # This is more complex to capture accurately within a method's scope.
            # A simpler approach for this subtask is to identify types used in signatures
            # and within the method body that aren't captured by the above.
            # This requires a more thorough traversal or a different approach,
            # but for this iteration, we'll focus on the explicit calls and creations.
            # We can add a placeholder for 'type_only' but comprehensive collection is harder now.
            if hasattr(node, 'type') and node.type and hasattr(node.type, 'name') and node.type.name in custom_classes:
                 full_path = custom_classes[node.type.name]
                 if full_path != main_class_full_path:
                     type_only_classes.add(full_path)


        # Process collected data for the current method
        method_dependencies = {
            class_name: sorted(list(methods))
            for class_name, methods in method_calls.items()
            if methods
        }

        # method_active_uses = {
        #     full_path: sorted(list(usages))
        #     for full_path, usages in actively_used_candidates.items()
        # }

        # Combine and refine results for the method
        combined_uses = {}
        for full_path, calls in method_dependencies.items():
            if full_path not in combined_uses:
                combined_uses[full_path] = set()
            for call in calls:
                # Method Call
                combined_uses[full_path].add(f"{call}")

        # for full_path, usages in method_active_uses.items():
        #     if full_path not in combined_uses:
        #         combined_uses[full_path] = set()
        #     for usage in usages:
        #         # Active Use
        #         combined_uses[full_path].add(f"Active Use: {usage}")

        # Add types that were used but not as calls or active uses
        for full_path in type_only_classes:
            if full_path not in combined_uses:
                 combined_uses[full_path] = set()
            combined_uses[full_path].add("Used By Type")


        # Format the results for the current method
        method_analysis_results[method_name] = {
            full_path: sorted(list(uses))
            for full_path, uses in combined_uses.items()
        }


    # Construct the final result dictionary for all methods
    final_result = {
        "inferred_base_package": BASE_PACKAGE,
        "analyzed_main_class": {
            "name": main_class_name,
            "package": main_class_package,
            "defined_methods": sorted(list(method_analysis_results.keys()))
        },
        "method_level_analysis": method_analysis_results
    }

    return final_result