
import sys
import os
import json
import copy
import ast

# 파이썬 경로에 프로젝트 루트 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from fastapi_client.graph.node import compare_to_rfp, vector_store

def print_all_rag_data():
    """
    RAG의 vector_store에 저장된 모든 데이터를 가져와 콘솔에 출력합니다.
    """
    try:
        print("\n--- RAG Vector Store 전체 데이터 확인 ---")
        # ChromaDB의 .get() 메서드를 사용하여 모든 데이터 가져오기
        all_data = vector_store.get() 
        num_documents = len(all_data.get('ids', []))
        print(f"Vector Store에 총 {num_documents}개의 문서가 저장되어 있습니다.")

        # 전체 문서의 내용과 메타데이터를 출력
        if num_documents > 0:
            print("\n[전체 데이터]")
            ids = all_data.get('ids', [])
            documents = all_data.get('documents', [])
            metadatas = all_data.get('metadatas', [])
            for i in range(num_documents):
                print(f"  - ID: {ids[i]}")
                print(f"    Metadata: {metadatas[i]}")
                # ast.literal_eval을 시도하여 딕셔너리 형태면 예쁘게 출력
                try:
                    doc_content = ast.literal_eval(documents[i])
                    if isinstance(doc_content, dict):
                         print(f"    Document: {json.dumps(doc_content, indent=6, ensure_ascii=False)}")
                    else:
                        raise ValueError
                except (ValueError, SyntaxError):
                    print(f"    Document: {documents[i]}")

                print("-" * 20)
        print("----------------------------------------\n")

    except Exception as e:
        print(f"\n[에러] RAG Vector Store 데이터 확인 중 오류 발생: {e}\n")

print_all_rag_data()

def test_code_compare_integration():
    """
    test_code_compare 노드의 통합 테스트.
    실제 RAG 파이프라인을 호출하여 요구사항 매칭을 수행하고 결과를 검증합니다.
    """
    # --- 0. RAG 데이터 확인 ---
    # print_all_rag_data()
    
    # --- 1. 입력 데이터 로드 ---
    test_dir = os.path.dirname(__file__)
    input_json_path = os.path.join(test_dir, 'test_data', 'input_compare_to_rfp.json')
    with open(input_json_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    original_state = copy.deepcopy(state)

    # --- 2. 노드 실행 (실제 RAG 호출) ---
    actual_output = compare_to_rfp(state)

    # --- 3. 결과 리포트 출력 ---
    print("\n\n--- compare_to_rfp 노드 출력 리포트 (실제 RAG 결과) ---")
    print(json.dumps(actual_output, indent=2, ensure_ascii=False))
    print("---------------------------------------------------------------------\n")

    # 결과를 JSON 파일로 저장
    output_filepath = 'compare_to_rfp_results.json'
    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(actual_output, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    test_code_compare_integration()