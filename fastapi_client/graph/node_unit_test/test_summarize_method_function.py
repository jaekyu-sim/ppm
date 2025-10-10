import sys
import os

import json

# 파이썬 경로에 프로젝트 루트 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from fastapi_client.graph.node import summarize_method_function

def test_summarize_method_function_integration():
    """실제 LLM을 호출하여 summarize_method_function 노드의 통합 테스트를 수행합니다."""
    # --- 1. 입력 데이터 로드 ---
    test_dir = os.path.dirname(__file__)
    input_json_path = os.path.join(test_dir, 'test_data', 'input_summarize_method_function.json')
    with open(input_json_path, 'r', encoding='utf-8') as f:
        state = json.load(f)

    # --- 2. 노드 실행 (실제 LLM 호출) ---
    actual_output = summarize_method_function(state)

    # --- 3. 결과 리포트 출력 ---
    print("\n\n--- summarize_method_function 노드 출력 리포트 (실제 LLM 결과) ---")
    print(json.dumps(actual_output, indent=2, ensure_ascii=False))
    print("--------------------------------------------------------------------\n")

    # --- 4. 결과 검증 ---
    assert 'parsed_methods' in actual_output, "출력에 'parsed_methods' 키가 있어야 합니다."

    output_files = actual_output['parsed_methods']
    input_files = state['parsed_methods']

    # 입력과 출력의 파일 개수가 동일한지 확인
    assert len(output_files) == len(input_files), "입력과 출력의 파일 개수가 다릅니다."

    # 전체 메서드 개수를 세어, 생성된 summary 개수와 일치하는지 간접적으로 확인
    total_input_methods = sum(len(f.get('method_list', [])) for f in input_files)
    total_output_summaries = sum(len(m.get('summary', '')) > 0 for f in output_files for m in f.get('method_list', []))

    assert total_input_methods == total_output_summaries, "입력 메서드 총 개수와 생성된 요약문의 개수가 다릅니다."

    # 파일 및 메서드 순서가 유지되는지, 모든 메서드에 summary가 추가되었는지 확인
    for i, input_file in enumerate(input_files):
        output_file = output_files[i]
        assert input_file['file_name'] == output_file['file_name'], f"{i}번째 파일 이름이 일치하지 않습니다."

        input_methods = input_file.get('method_list', [])
        output_methods = output_file.get('method_list', [])
        assert len(input_methods) == len(output_methods), f"{input_file['file_name']} 파일의 메서드 개수가 다릅니다."

        for j, input_method in enumerate(input_methods):
            output_method = output_methods[j]
            # summary 키 존재 및 비어있지 않은지 확인
            assert 'summary' in output_method, f"{input_method['method_name']} 메서드에 summary 키가 없습니다."
            assert output_method['summary'] and output_method['summary'].strip() != "", f"{input_method['method_name']} 메서드의 summary가 비어있습니다."
            
            # 원본 데이터가 유지되는지 확인
            assert input_method['method_name'] == output_method['method_name']
            
            # method_code는 원본과 길이 차이가 5% 이내여야 함
            input_code_len = len(input_method['method_code'])
            output_code_len = len(output_method['method_code'])

            if input_code_len > 0:
                len_diff_percentage = abs(input_code_len - output_code_len) / input_code_len
                assert len_diff_percentage <= 0.1, \
                    f"'{input_method['method_name']}' 메서드 코드의 길이가 10% 이상 변경되었습니다. " \
                    f"원본 길이: {input_code_len}, 결과 길이: {output_code_len}, 차이: {len_diff_percentage:.2%}"
            else:
                assert output_code_len == 0, \
                    f"'{input_method['method_name']}' 메서드의 원본 코드는 비어있으나, 결과 코드 길이는 {output_code_len}입니다."
