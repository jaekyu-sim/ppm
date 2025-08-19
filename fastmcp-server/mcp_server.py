# 가상환경 실행 : .\.venv\Scripts\activate.ps1

from github import Github
from mcp.server.fastmcp import FastMCP
import base64
from typing import TypedDict, List, Literal, NotRequired


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

# dev : mcp dev ./fastmcp-server/mcp_server.py
# prd : python ./fastmcp-server/mcp_server.py 
if __name__ == "__main__":
    mcp.run(transport="stdio")
