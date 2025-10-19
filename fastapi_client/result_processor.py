from typing import Any, Dict
import json
from github_service import post_pr_comment, create_gist

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
        markdown += "| 기능정합성 | 입력정합성 | 처리정합성 | 출력정합성 |\n"
        markdown += "|------------|------------|------------|------------|\n"
        markdown += f"| {scores.get('기능정합성', 0.0):.2f} | {scores.get('입력정합성', 0.0):.2f} | {scores.get('처리정합성', 0.0):.2f} | {scores.get('출력정합성', 0.0):.2f} |\n\n"

        markdown += "#### 📝 요구사항 분석\n"
        markdown += "| 항목 | 내용 |\n"
        markdown += "|------|------|\n"
        raw_block = item.get('raw_block', {})
        markdown += f"| **목적** | {raw_block.get('purpose', '')} |\n"
        markdown += f"| **입력** | {raw_block.get('input', '')} |\n"
        markdown += f"| **처리** | {raw_block.get('processing', '')} |\n"
        markdown += f"| **출력** | {raw_block.get('output', '')} |\n"

        missing_points = item.get('missing_points', [])
        if missing_points:
            markdown += "#### ⚠️ 미충족 사항\n"
            for point in missing_points:
                markdown += f"- {point}\n"
        
        if i < len(answer):
            markdown += "\n---\n\n"

    return markdown

def format_debug_info(debug_data: Dict[str, Any], repo_full_name: str, pr_number: int) -> str:
    """
    디버그 정보를 포맷하고, 원시 데이터를 Gist에 생성한 후 마크다운 문자열을 반환합니다.
    """
    debug_markdown = "## 🕵️ 디버그 정보\n\n"
    
    # 전체 디버그 데이터를 Gist에 생성
    json_content = json.dumps(debug_data, indent=2, ensure_ascii=False)
    gist_url = create_gist(
        file_name=f"pr_{pr_number}_debug_output.json",
        file_content=json_content,
        description=f"Debug output for PR #{pr_number} in {repo_full_name}"
    )

    if gist_url:
        debug_markdown += f"- **전체 결과 (JSON):** [Gist에서 확인]({gist_url})\n"
    else:
        debug_markdown += "- **전체 결과 (JSON):** Gist 생성에 실패했습니다.\n"
        
    debug_markdown += "\n---\n\n"
    return debug_markdown

def process_code_comparison_result(
    final_result: Dict[str, Any], 
    repo_full_name: str, 
    commit_sha: str,
    pr_comment_send: bool, 
    pr_number: int | None,
    pr_comment_debug: bool = False
) -> str:
    
    debug_markdown = ""
    # 디버그 모드가 켜져 있으면 디버그 정보를 생성하고 포맷합니다.
    if pr_comment_debug and pr_number and repo_full_name:
        debug_markdown = format_debug_info(final_result, repo_full_name, pr_number)

    markdown_output = format_final_result_to_markdown(final_result, repo_full_name, commit_sha)
    
    # 디버그 마크다운을 메인 출력 앞에 추가합니다.
    final_markdown = debug_markdown + markdown_output

    # PR 코멘트 등록 로직
    if pr_comment_send is True:
        if pr_number and repo_full_name:
            # 합쳐진 마크다운을 코멘트로 게시합니다.
            post_pr_comment(repo_full_name, pr_number, final_markdown)
        else:
            print("PR 번호 또는 리포지토리 이름을 찾을 수 없어 코멘트를 등록하지 못했습니다.")
    
    return final_markdown

def format_final_result_to_markdown(json_data: dict, repository: str, sha: str) -> str:
    answer = json_data.get("answer", [])
    file_code_map = {f.get("file_name").split('/')[-1]: f.get("file_name") for f in json_data.get("file_code", [])}

    if not answer:
        return "# 📊 요구사항 정합성 검증 결과\n\n검증 결과가 없습니다."

    # 1. 전체 결과 요약
    total_count = len(answer)
    fulfilled_count = sum(1 for item in answer if item['decision'] == '충족')
    partially_fulfilled_count = sum(1 for item in answer if item['decision'] == '부분충족')
    unfulfilled_count = sum(1 for item in answer if item['decision'] == '미충족')
    progress_rate = (fulfilled_count / total_count) * 100 if total_count > 0 else 0

    rfp_number = json_data.get("tmp_rfp_number", "N/A")
    markdown = f"# 📊 {rfp_number} 요구사항 정합성 검증 결과\n\n"
    markdown += "## 📈 전체 결과 요약\n\n"
    markdown += "| 전체 항목 | ✅ 충족 | 🟡 부분 충족 | 🔴 미충족 | 개발진척율 |\n"
    markdown += "| :---: | :---: | :---: | :---: | :---: |\n"
    markdown += f"| {total_count} | {fulfilled_count} | {partially_fulfilled_count} | {unfulfilled_count} | {progress_rate:.0f}% |\n\n"

    # 2. 상세 요구사항별 결과
    markdown += "## 📋 상세 요구사항별 결과\n\n"
    markdown += "| No | 상세 요구사항 | 내용 | 충족도 | 종합 점수 |\n"
    markdown += "| :--- | :--- | :--- | :---: | :---: |\n"
    decision_to_icon = {
        "충족": "✅",
        "부분충족": "🟡",
        "미충족": "🔴"
    }
    for i, item in enumerate(answer, 1):
        decision_text = f"{decision_to_icon.get(item['decision'], '')} {item['decision']}"
        markdown += f"| {i} | {item['rfp_id']} | {item['rfp_contents']['content']} | {decision_text} | {item['total_score']:.2f} |\n"

    markdown += "\n<br/>\n\n"

    # 3. 상세 요구사항별 상세
    for item in answer:
        markdown += "\n---\n\n<br/>\n\n"
        markdown += f"## {item['rfp_id']} : {item['rfp_contents']['content']}\n\n"
        
        # 요구사항, 검증 결과, 요약, 종합 점수
        decision_text = f"{decision_to_icon.get(item['decision'], '')} **{item['decision']}**"
        markdown += f"- **구현 시 참고사항**: {item['rfp_contents']['reference']}\n"
        markdown += f"- **검증 결과**: {decision_text}\n\n"
        markdown += f"  - {item['summary']}\n\n"
        markdown += f"- **종합 점수**: {item['total_score']:.2f}\n\n"

        # 상세 점수
        scores = item['scores']
        markdown += "  | 기능정합성 | 입력정합성 | 처리정합성 | 출력정합성 |\n"
        markdown += "  | :---: | :---: | :---: | :---: |\n"
        markdown += f"  | {scores.get('기능정합성', 0.0):.2f} | {scores.get('입력정합성', 0.0):.2f} | {scores.get('처리정합성', 0.0):.2f} | {scores.get('출력정합성', 0.0):.2f} |\n"

        # 보완 필요 사항
        if item.get('missing_points'):
            markdown += "> [!WARNING]\n"
            markdown += "> ⚠️ **보완 필요 사항**\n"
            for point in item['missing_points']:
                markdown += f"> - {point}\n"

        # 추적된 함수 목록
        markdown += "\n### 🔍 추적된 함수 목록\n\n"
        markdown += "  | File | Function | Link |\n"
        markdown += "  | :--- | :--- | :--- |\n"
        for func in item['trace']['matched_functions']:
            short_filename = func['file'].split('.')[-2] + '.java'
            full_path = file_code_map.get(short_filename, func['file'])
            link = f"[Link](https://github.com/{repository}/blob/{sha}/{full_path})"
            markdown += f"  | {short_filename} | {func['name']} | {link} |\n"

        # 함수 상세
        markdown += "\n### ⚙️ 함수 상세\n\n"
        for func in item['trace']['matched_functions']:
            short_filename = func['file'].split('.')[-2] + '.java'
            markdown += f"  <details>\n<summary>{short_filename} - {func['name']}</summary>\n\n"
            markdown += f"- **파일:** {func['file']}\n"
            markdown += f"- **기능:** {func['purpose']}\n"
            markdown += f"- **입력:** {func['input']}\n"
            markdown += f"- **처리:** {func['processing']}\n"
            markdown += f"- **출력:** {func['output']}\n"
            markdown += f"- **예외:** {func['exceptions']}\n"
            markdown += "  </details>\n"

    return markdown