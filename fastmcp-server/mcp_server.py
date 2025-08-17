# 가상환경 실행 : .\.venv\Scripts\activate.ps1

from github import Github
from mcp.server.fastmcp import FastMCP
import base64

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
def get_changed_files_from_commit(repo_name: str, commit_sha: str) -> list[str]:
    """특정 GitHub 커밋에서 변경된 파일 목록을 가져옵니다.

    Args:
        repo_name (str): GitHub 리포지토리 이름 (예: 'owner/repo').
        commit_sha (str): 파일 변경 목록을 가져올 커밋의 SHA.

    Returns:
        list[str]: 변경된 파일의 경로 목록.
    """
    try:
        g = Github()
        repo = g.get_repo(repo_name)
        commit = repo.get_commit(sha=commit_sha)
        return [file.filename for file in commit.files]
    except Exception as e:
        return [f"An error occurred: {e}"]

@mcp.tool()
def get_file_content(repo_full_name: str, file_path: str, ref: str = 'main') -> str | None:
    """GitHub 리포지토리에서 특정 파일의 내용을 가져옵니다.

    Args:
        repo_full_name (str): GitHub 리포지토리의 전체 이름 (예: 'owner/repo').
        file_path (str): 내용을 가져올 파일의 경로.
        ref (str, optional): 브랜치, 태그 또는 커밋 SHA. 기본값은 'main'입니다.

    Returns:
        str | None: 파일 내용 (문자열) 또는 실패 시 None.
    """
    try:
        g = Github()
        repo = g.get_repo(repo_full_name)
        contents = repo.get_contents(file_path, ref=ref)
        if contents.encoding == "base64":
            return base64.b64decode(contents.content).decode('utf-8')
        else:
            return contents.decoded_content.decode('utf-8')
    except Exception as e:
        return [f"An error occurred in get_file_content: {e}"]

# dev : mcp dev ./fastmcp-server/mcp_server.py
# prd : python ./fastmcp-server/mcp_server.py 
if __name__ == "__main__":
    mcp.run(transport="stdio")
