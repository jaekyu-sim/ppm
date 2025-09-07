# 가상환경 실행 : .\.venv\Scripts\activate.ps1

from github import Github
from mcp.server.fastmcp import FastMCP
import base64
from typing import TypedDict, List, Literal, NotRequired, Union
import os
from dotenv import load_dotenv
import re
import requests
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_ollama.chat_models import ChatOllama

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- 데이터 구조 정의 ---
class ChangedFile(TypedDict):
    fileName: str
    code: str

class CommitDetails(TypedDict):
    resultStatus: Literal['success', 'error']
    author: NotRequired[str]
    email: NotRequired[str]
    message: NotRequired[str]
    sha: NotRequired[str]
    files: NotRequired[List[ChangedFile]]

class MethodLocation(TypedDict):
    method_name: str
    start_line: int
    end_line: int
    code: str

mcp = FastMCP("ppm")

@mcp.tool()
def add(a: int, b: int) -> int:
    """두 숫자를 더하는 함수입니다.

    Args:
        a (int): 첫 번째 숫자.
        b (int): 두 번째 숫자.

    Returns:
        int: 두 숫자를 더한 결과.
    """
    return a + b

@mcp.tool()
def get_commit_data(repo_name: str, commit_sha: str) -> CommitDetails:
    """특정 GitHub 커밋에서 변경된 파일의 내용 목록을 가져옵니다.

    Args:
        repo_name (str): GitHub 리포지토리 이름 (예: 'owner/repo').
        commit_sha (str): 파일 변경 내용을 가져올 커밋의 SHA.

    Returns:
        CommitDetails: 커밋 정보와 변경된 파일의 상세 정보 또는 에러 메시지가 담긴 공통 응답 딕셔너리.
    """
    try:
        g = Github()

        repo = g.get_repo(repo_name) # TODO: 부적합한 repo_name 예외처리
        commit = repo.get_commit(sha=commit_sha) # TODO: 부적합한 commit_sha 예외처리
        
        author = commit.commit.author.name
        email = commit.commit.author.email
        message = commit.commit.message
        sha = commit.sha

        files_list = []
        for file in commit.files:
            # 파일 제거의 경우는 무시
            if file.status == 'removed':
                continue
            
            file_path = file.filename
            try:
                content_item = repo.get_contents(file_path, ref=commit_sha)
                
                if content_item.encoding == "base64":
                    code = base64.b64decode(content_item.content).decode('utf-8')
                else:
                    code = content_item.decoded_content.decode('utf-8')

                files_list.append({
                    "fileName": file_path,
                    "code": code
                })
            except Exception as e:
                print(f"Error fetching content for {file_path}: {e}")

        return {
            "resultStatus": "success",
            "author": author,
            "email": email,
            "message": message,
            "sha": sha,
            "files": files_list
        }
    except Exception as e:
        print(f"An overall error occurred: {e}")
        return {
            "resultStatus": "error"
        }


prompt_template = """당신은 매우 정확하고, 지시를 엄격하게 따르는 코드 분석 전문가입니다. 당신의 임무는 주어진 소스 코드에서 변경된 라인 번호에 해당하는 **모든** 메서드나 함수를 **하나도 빠짐없이** 찾아내는 것입니다.

다음은 `{file_path}` 파일의 전체 소스 코드입니다:
```
{full_code}
```

최근 변경된 코드의 라인 번호 범위는 다음과 같습니다: `{changed_lines_str}`.

**지시사항:**
1.  **변경 라인 주변 탐색**: 주어진 변경 라인 범위(`{changed_lines_str}`)를 중심으로, 해당 범위와 겹치거나 인접한 메서드/함수를 찾습니다.
2.  **메서드 경계 식별**: 찾은 각 메서드/함수에 대해 정확한 시작 라인과 끝 라인을 식별합니다.
3.  **누락 없이 수집**: 변경된 라인 범위와 관련된 모든 메서드를 리스트에 추가해야 합니다.
4.  **정확한 JSON 형식**: 결과는 아래 명시된 JSON 형식과 정확히 일치해야 합니다. 메서드를 찾지 못한 경우에는 빈 리스트 `[]`를 반환해야 합니다.

찾은 각 메서드에 대해 이름, 시작 라인 번호, 끝 라인 번호, 그리고 해당 메서드의 전체 코드를 제공해 주세요.

**JSON 출력 형식:**
- **JSON 객체 배열(리스트)**로 응답해 주세요.
- 각 객체는 `method_name`, `start_line`, `end_line`, `code` 키를 가져야 합니다.

**예시 응답 (2개의 메서드를 찾은 경우):**
[
  {{
    "method_name": "firstExampleMethod",
    "start_line": 10,
    "end_line": 25,
    "code": "public void firstExampleMethod() {{...}}"
  }},
  {{
    "method_name": "secondExampleMethod",
    "start_line": 30,
    "end_line": 45,
    "code": "public void secondExampleMethod() {{...}}"
  }}
]

응답에 JSON 배열 외에 다른 설명이나 텍스트를 포함하지 마세요.
"""

m = ChatOllama(model="qwen3:4b", temperature=0)
prompt = ChatPromptTemplate.from_template(prompt_template)
chain = prompt | m | JsonOutputParser()

def _extract_methods_with_llm(file_path: str, full_code: str, hunk_ranges: List[str]) -> List[MethodLocation]:
    try:
        changed_lines_str = ", ".join(hunk_ranges)
        
        invoke_input = {
            "file_path": file_path,
            "full_code": full_code,
            "changed_lines_str": changed_lines_str
        }

        # 1. Render the full prompt and print it
        final_prompt = prompt.format_prompt(**invoke_input)
        print("---" + "-" * 10 + " FINAL PROMPT " + "-" * 10 + "---")
        print(final_prompt.to_string())
        print("--------------------")

        # Get raw response from the model
        model_chain = prompt | m
        raw_llm_output = model_chain.invoke(invoke_input)

        print("---" + "-" * 10 + " RAW LLM OUTPUT " + "-" * 10 + "---")
        print(raw_llm_output.content)
        print("--------------------")

        # Parse the raw response
        output_parser = JsonOutputParser()
        llm_result = output_parser.parse(raw_llm_output.content)

        if isinstance(llm_result, list):
            return llm_result
        # Handle cases where the model might return a single dict
        elif isinstance(llm_result, dict):
            return [llm_result]
        else:
            print(f"LLM output was not a list or a dict: {llm_result}")
            return []

    except Exception as e:
        print(f"Error extracting methods with LLM for {file_path}: {e}")
        return []

    except Exception as e:
        print(f"Error extracting methods with LLM for {file_path}: {e}")
        return []

def parse_diff(diff_content):
    """
    git diff 내용을 파싱하여 변경된 파일과, '+' 또는 '-'로 표시된
    정확한 변경 라인 번호 범위를 추출합니다.
    """
    files_diffs = diff_content.split('diff --git')
    analysis_results = []

    for file_diff in files_diffs:
        if not file_diff.strip():
            continue

        path_match = re.search(r'\n\+\+\+ b/(.*?)\n', file_diff)
        if not path_match:
            continue
        file_path = path_match.group(1)

        if 'new file mode' in file_diff:
            analysis_results.append({
                "file_path": file_path,
                "hunk_ranges": "전체"
            })
            continue

        changed_lines = []
        # Hunk content is between @@ markers
        hunks = re.split(r'@@ -.*? \+.*? @@', file_diff)
        # Hunk headers contain the line numbers
        hunk_headers = re.findall(r'@@ -.*? \+(\d+),?(\d*) @@', file_diff)

        # The first element from split is before the first hunk, so we skip it.
        for i, hunk_body in enumerate(hunks[1:]):
            if i >= len(hunk_headers):
                break
            
            header_info = hunk_headers[i]
            current_line_num = int(header_info[0])
            
            # The first line of hunk_body is an empty string, so skip it
            for line in hunk_body.split('\n')[1:]:
                if line.startswith('+'):
                    changed_lines.append(current_line_num)
                
                if not line.startswith('-'):
                    current_line_num += 1
        
        if changed_lines:
            # Consolidate consecutive line numbers into ranges
            if not changed_lines:
                continue
            
            ranges = []
            start = changed_lines[0]
            end = changed_lines[0]
            for i in range(1, len(changed_lines)):
                if changed_lines[i] == end + 1:
                    end = changed_lines[i]
                else:
                    if start == end:
                        ranges.append(f"{start}")
                    else:
                        ranges.append(f"{start}-{end}")
                    start = changed_lines[i]
                    end = changed_lines[i]
            
            if start == end:
                ranges.append(f"{start}")
            else:
                ranges.append(f"{start}-{end}")

            analysis_results.append({
                "file_path": file_path,
                "hunk_ranges": ranges
            })
            
    return analysis_results

@mcp.tool()
def extract_methods_from_pr_diff(repo_name: str, pr_number: int) -> CommitDetails:
    """GitHub PR의 diff를 파싱하여 변경된 라인에 속한 메서드의 코드를 추출합니다."""
    try:
        g = Github(os.getenv("GITHUB_TOKEN"))
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        head_sha = pr.head.sha

        diff_url = f"https://patch-diff.githubusercontent.com/raw/{repo_name}/pull/{pr_number}.diff"
        response = requests.get(diff_url)
        response.raise_for_status()
        diff_content = response.text

        if not diff_content:
            return {
                "resultStatus": "success",
                "author": pr.user.login,
                "sha": pr.head.sha,
                "message": pr.title,
                "files": []
            }

        parsed_diff = parse_diff(diff_content)
        
        output_files: List[ChangedFile] = []

        for file_info in parsed_diff:
            file_path = file_info["file_path"]
            hunk_ranges = file_info["hunk_ranges"]

            print(f"Analyzing file: {file_path} (Changed lines: {hunk_ranges})")
            
            code_content = ""
            if hunk_ranges == "전체":
                try:
                    content_obj = repo.get_contents(file_path, ref=head_sha)
                    code_content = content_obj.decoded_content.decode('utf-8')
                except Exception as e:
                    print(f"Error fetching content for {file_path}: {e}")
            else:
                try:
                    content_obj = repo.get_contents(file_path, ref=head_sha)
                    content = content_obj.decoded_content.decode('utf-8')
                    
                    methods: List[MethodLocation] = _extract_methods_with_llm(file_path, content, hunk_ranges)
                    
                    if methods:
                        # 여러 메서드 코드를 하나의 문자열로 합침
                        code_content = "\n\n".join(method['code'] for method in methods)
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
            
            if code_content:
                output_files.append({
                    "fileName": file_path,
                    "code": code_content
                })

        return {
            "resultStatus": "success",
            "author": pr.user.login,
            "sha": pr.head.sha,
            "message": pr.title,
            "files": output_files
        }

    except Exception as e:
        print(f"전체 프로세스 오류 발생: {e}")
        return {"resultStatus": "error", "message": str(e)}


@mcp.tool()
def post_pr_comment(repo_name: str, pr_number: int, body: str) -> dict:
    """GitHub PR에 코멘트를 남깁니다."""
    try:
        g = Github(os.getenv("GITHUB_TOKEN"))
        repo = g.get_repo(repo_name)
        pull = repo.get_pull(pr_number)
        pull.create_issue_comment(body)
        return {"resultStatus": "success"}
    except Exception as e:
        print(f"An error occurred: {e}")
        return {"resultStatus": "error", "message": str(e)}

# dev : mcp dev ./fastmcp-server/mcp_server.py
# prd : python ./fastmcp-server/mcp_server.py 
if __name__ == "__main__":
    # 테스트용 코드
    # repo_name="HorangApple/sports-portal"
    # pr_number=2
    # extract_methods_from_pr_diff(repo_name, pr_number)
    mcp.run(transport="stdio")
