import base64
import logging
import os
from typing import List, TypedDict, Dict

from dotenv import load_dotenv
from github import Github, InputFileContent

# .env 파일에서 환경 변수 로드
load_dotenv()
g = Github(os.getenv("GITHUB_TOKEN"))

logger = logging.getLogger(__name__)

# --- 데이터 구조 ---
class FileContent(TypedDict):
    file_name: str
    code: str

class ChangedFilesContent(TypedDict):
    sha: str
    file_list: List[FileContent]

# --- 메인 함수 ---
def get_files_content_by_sha(
    repo_full_name: str, 
    file_paths: List[str], 
    sha: str
) -> ChangedFilesContent:
    """
    주어진 SHA를 기준으로 파일 경로 리스트에 해당하는 파일들의 전체 소스 코드를 반환합니다.
    """
    files_content_list: List[FileContent] = []
    try:
        repo = g.get_repo(repo_full_name)
        for file_path in file_paths:
            try:
                content_item = repo.get_contents(file_path, ref=sha)
                code = base64.b64decode(content_item.content).decode('utf-8') if content_item.encoding == "base64" else content_item.decoded_content.decode('utf-8')
                files_content_list.append({"file_name": file_path, "code": code})
            except Exception as e:
                logger.warning(f"Error fetching content for {file_path} at SHA {sha}: {e}")
    except Exception as e:
        logger.error(f"An overall error occurred while fetching files content: {e}")
        return {"sha": sha, "file_list": []}
    return {"sha": sha, "file_list": files_content_list}

def get_pr_changed_files_content(
    repo_full_name: str, 
    pr_number: int
) -> ChangedFilesContent:
    """
    Pull Request에서 변경된 파일 목록을 가져와 해당 파일들의 전체 소스 코드를 반환합니다.
    """
    try:
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        head_sha = pr.head.sha
        changed_files_paths = [file.filename for file in pr.get_files()]
        return get_files_content_by_sha(repo_full_name, changed_files_paths, head_sha)
    except Exception as e:
        logger.error(f"Error getting PR changed files content for PR #{pr_number}: {e}")
        return {"sha": "", "file_list": []}

def get_commit_changed_files_content(
    repo_full_name: str, 
    commit_sha: str
) -> ChangedFilesContent:
    """
    특정 커밋에서 변경된 파일 목록을 가져와 해당 파일들의 전체 소스 코드를 반환합니다.
    """
    try:
        repo = g.get_repo(repo_full_name)
        commit = repo.get_commit(sha=commit_sha)
        changed_files_paths = [file.filename for file in commit.files if file.status != 'removed']
        return get_files_content_by_sha(repo_full_name, changed_files_paths, commit_sha)
    except Exception as e:
        logger.error(f"Error getting commit changed files content for commit {commit_sha}: {e}")
        return {"sha": commit_sha, "file_list": []}

def get_diff_files_content_between_branches(
    repo_full_name: str,
    base_branch: str,
    compare_branch: str
) -> ChangedFilesContent:
    """
    두 브랜치 간에 변경된 파일 목록을 가져와 비교 브랜치 기준으로 해당 파일들의 전체 소스 코드를 반환합니다.
    """
    try:
        repo = g.get_repo(repo_full_name)
        compare_branch_obj = repo.get_branch(compare_branch)
        compare_branch_sha = compare_branch_obj.commit.sha
        comparison = repo.compare(base_branch, compare_branch)
        changed_files_paths = [file.filename for file in comparison.files if file.status != 'removed']
        return get_files_content_by_sha(repo_full_name, changed_files_paths, compare_branch_sha)
    except Exception as e:
        logger.error(f"Error getting diff files content between {base_branch} and {compare_branch}: {e}")
        return {"sha": "", "file_list": []}

def post_pr_comment(repo_full_name: str, pr_number: int, body: str) -> Dict[str, str]:
    """
    지정된 Pull Request에 코멘트를 게시합니다.
    """
    try:
        repo = g.get_repo(repo_full_name)
        pull = repo.get_pull(pr_number)
        pull.create_issue_comment(body)
        return {"resultStatus": "success"}
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return {"resultStatus": "error", "message": str(e)}

def create_gist(file_name: str, file_content: str, description: str) -> str | None:
    """
    주어진 내용으로 비공개 GitHub Gist를 생성합니다.
    """
    try:
        user = g.get_user()
        gist = user.create_gist(
            public=False,
            files={file_name: InputFileContent(file_content)},
            description=description
        )
        return gist.html_url
    except Exception as e:
        logger.error(f"Failed to create Gist: {e}")
        return None

if __name__ == "__main__":
    # Constants for testing
    TEST_REPO = "HorangApple/sports-portal"
    TEST_PR_NUMBER = 3
    TEST_COMMIT_SHA = "beff35bf72321a4e8cd9aaf4e4b068425ed4e798"
    TEST_BASE_BRANCH = "dev_main"
    TEST_COMPARE_BRANCH = "SFR-113"

    # print("--- Testing get_pr_changed_files_content ---")
    # pr_content = get_pr_changed_files_content(TEST_REPO, TEST_PR_NUMBER)
    # print(f"PR SHA: {pr_content['sha']}")
    # print(f"Total files in PR: {len(pr_content['file_list'])}")
    # for file_data in pr_content['file_list']:
    #     print(f"  File: {file_data['file_name']}")
    #     # print(f"    Code: {file_data['code'][:100]}...")
    # print("-" * 50)

    # print("--- Testing get_commit_changed_files_content ---")
    # commit_content = get_commit_changed_files_content(TEST_REPO, TEST_COMMIT_SHA)
    # print(f"Commit SHA: {commit_content['sha']}")
    # print(f"Total files in Commit: {len(commit_content['file_list'])}")
    # for file_data in commit_content['file_list']:
    #     print(f"  File: {file_data['file_name']}")
    #     # print(f"    Code: {file_data['code'][:100]}...")
    # print("-" * 50)

    # print("--- Testing get_diff_files_content_between_branches ---")
    # diff_content = get_diff_files_content_between_branches(TEST_REPO, TEST_BASE_BRANCH, TEST_COMPARE_BRANCH)
    # print(f"Compare Branch SHA: {diff_content['sha']}")
    # print(f"Total files in Diff: {len(diff_content['file_list'])}")
    # for file_data in diff_content['file_list']:
    #     print(f"  File: {file_data['file_name']}")
    #     # print(f"    Code: {file_data['code'][:100]}...")
    # print("-" * 50)

    # print("--- Testing post_pr_comment ---")
    # comment_body = "This is a test comment from the script."
    # result = post_pr_comment(TEST_REPO, TEST_PR_NUMBER, comment_body)
    # print(f"Post comment result: {result}")
    # print("-" * 50)