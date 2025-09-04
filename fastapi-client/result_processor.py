from typing import Any, Dict
from github import Github
import os
from dotenv import load_dotenv

load_dotenv()

async def post_pr_comment(mcp_client: Any, repo_full_name: str, pr_number: int, body: str):

    try:
        g = Github(os.getenv("GITHUB_TOKEN"))
        repo = g.get_repo(repo_full_name)
        pull = repo.get_pull(pr_number)
        pull.create_issue_comment(body)
        return {"resultStatus": "success"}
    except Exception as e:
        print(f"An error occurred: {e}")
        return {"resultStatus": "error", "message": str(e)}
    

def format_compare_result_to_markdown(compare_result: Dict[str, Any]) -> str:

    answer = compare_result.get('answer', [])
    if not answer:
        return "# 📊 요구사항 정합성 검증 결과\n\n검증 결과가 없습니다."

    # 1. 전체 결과 요약
    total_count = len(answer)
    fulfilled_count = sum(1 for item in answer if item['decision'] == '충족')
    partially_fulfilled_count = sum(1 for item in answer if item['decision'] == '부분충족')
    unfulfilled_count = sum(1 for item in answer if item['decision'] == '미충족')
    
    # 개발진척율: '충족' 상태인 항목의 비율
    progress_rate = (fulfilled_count / total_count) * 100 if total_count > 0 else 0

    markdown = "# 📊 요구사항 정합성 검증 결과\n\n"
    markdown += "## 📈 전체 결과 요약\n"
    markdown += "| 전체 검증 | ✅ 충족 | 🟡 부분충족 | 🔴 미충족 | 개발진척율 |\n"
    markdown += "|-----------|---------|-------------|-----------|------------|\n"
    markdown += f"| {total_count}개 | {fulfilled_count}개 | {partially_fulfilled_count}개 | {unfulfilled_count}개 | {progress_rate:.0f}% |\n\n"

    # 2. 검증 결과 요약
    markdown += "## 🎯 검증 결과 요약\n\n"
    markdown += "| No. | 함수명 | 충족도 | 종합점수 |\n"
    markdown += "|-----|--------|--------|----------|\n"
    
    decision_to_icon = {
        "충족": "✅ 충족",
        "부분충족": "🟡 부분충족",
        "미충족": "🔴 미충족"
    }

    for i, item in enumerate(answer, 1):
        decision_text = decision_to_icon.get(item['decision'], item['decision'])
        markdown += f"| {i} | {item['function_name']} | {decision_text} | {item['total_score']:.2f} |\n"
    
    markdown += "\n"

    # 3. 상세 검증 결과
    markdown += "## 📋 상세 검증 결과\n\n"
    for i, item in enumerate(answer, 1):
        decision_text = decision_to_icon.get(item['decision'], item['decision'])
        markdown += f"### {i}. {item['function_name']}\n"
        markdown += f"**충족도**: {decision_text} ({item['total_score']:.2f})\n\n"
        
        scores = item['scores']
        markdown += "| 기능정합성 | 입력정합성 | 처리정합성 | 출력정합성 | 예외정합성 | 코드위험성 |\n"
        markdown += "|------------|------------|------------|------------|------------|------------|\n"
        markdown += f"| {scores.get('기능정합성', 0.0):.2f} | {scores.get('입력정합성', 0.0):.2f} | {scores.get('처리정합성', 0.0):.2f} | {scores.get('출력정합성', 0.0):.2f} | {scores.get('예외정합성', 0.0):.2f} | {scores.get('코드위험성', 0.0):.2f} |\n\n"

        markdown += "#### 📝 요구사항 분석\n"
        markdown += "| 항목 | 내용 |\n"
        markdown += "|------|------|\n"
        raw_block = item.get('raw_block', {})
        markdown += f"| **목적** | {raw_block.get('purpose', '')} |\n"
        markdown += f"| **입력** | {raw_block.get('input', '')} |\n"
        markdown += f"| **처리** | {raw_block.get('processing', '')} |\n"
        markdown += f"| **출력** | {raw_block.get('output', '')} |\n"
        markdown += f"| **예외** | {raw_block.get('exceptions', '')} |\n\n"

        missing_points = item.get('missing_points', [])
        if missing_points:
            markdown += "#### ⚠️ 미충족 사항\n"
            for point in missing_points:
                markdown += f"- {point}\n"
        
        if i < len(answer):
            markdown += "\n---\n\n"

    return markdown

async def process_code_comparison_result(mcp_client: Any, final_result: Dict[str, Any], repo_full_name: str, pr_comment_send: bool, pr_number: int | None) -> str:
    
    markdown_output = format_compare_result_to_markdown(final_result)

    # PR 코멘트 등록 로직
    if pr_comment_send is True:
        if pr_number and repo_full_name:
            await post_pr_comment(mcp_client, repo_full_name, pr_number, markdown_output)
        else:
            print("PR 번호 또는 리포지토리 이름을 찾을 수 없어 코멘트를 등록하지 못했습니다.")
    
    return markdown_output