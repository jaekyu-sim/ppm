# 가상환경 실행 : .\.venv\Scripts\activate.ps1

import json
import os
import re
from pathlib import Path

from langchain.schema import Document
from langchain_chroma import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_ollama import ChatOllama

# model cell

embeddings = OllamaEmbeddings(
    model="bge-m3"
)

llm = ChatOllama(
    model="qwen3:4b-instruct-2507-q8_0"
)

persist_directory = "./fastapi_client/chroma_db"
collection_name = 'requirements_list'

def extract_output_after_removing_think(text: str, return_json=False):
    no_think = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    blocks = re.findall(r"<output>.*?</output>", no_think, flags=re.DOTALL | re.IGNORECASE)

    picked = None
    for b in reversed(blocks):
        if re.search(r"<output>\s*\S", b, flags=re.DOTALL | re.IGNORECASE):
            picked = b
            break

    if picked is None:
        return None

    if return_json:
        return json.loads(picked) 
    else:
        return picked

def load_or_build_vector_store():
    print("[DEBUG] cwd       =", Path.cwd())
    if os.path.exists('./fastapi_client/chroma_db') and len(os.listdir('./fastapi_client/chroma_db')) > 0:
        #기존 벡터 DB 가 존재할 경우.
        print("Vector DB 존재. 불러오기 시작.")
        collection_name = 'requirements_list'
        persist_directory = "./fastapi_client/chroma_db"
        
        vector_store = Chroma(
            embedding_function=embeddings,
            collection_name = collection_name,
            persist_directory = persist_directory
        )
        print("Vector DB 불러오기 완료.")
        return vector_store, embeddings
    else:
        print("Vector DB 부재. 생성 시작.")
        # 1. 문서 로드
        base_dir = Path(__file__).resolve().parent  
        file_path = base_dir / "docs" / "vector_db_data.json"

        with open(file_path, "r", encoding="utf-8") as f:
            vector_db_data = json.load(f)


        vector_db_items = []
        for idx1, sfr in enumerate(vector_db_data):
            for idx2, detail_sfr in enumerate(sfr['구현항목']):
                req_id = vector_db_data[idx1]['요구사항ID']
                sub_item_id = detail_sfr['하위ID']
                #str_detail_sft = json.dumps(detail_sfr)
                str_detail_sft = str(detail_sfr)
                # print(req_id)
                # print(sub_item_id)
                # print(detail_sfr)
                doc = Document(page_content=str_detail_sft,metadata={"source": req_id, "list_name": sub_item_id, "idx": idx2})
                vector_db_items.append(doc)

        # 3. 벡터 스토어 생성
        persist_directory = "./fastapi_client/chroma_db"
        collection_name = 'requirements_list'
        vector_store = Chroma.from_documents(
            documents=vector_db_items, 
            embedding=embeddings, 
            persist_directory=persist_directory,
            collection_name=collection_name    
        )
        print("Vector DB 생성 완료.")

        return vector_store, embeddings


