# 가상환경 실행 : .\.venv\Scripts\activate.ps1

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
#from langchain.embeddings import OllamaEmbeddings #=> deprecated
from langchain_community.embeddings import OllamaEmbeddings
from langchain_chroma import Chroma
#from langchain_community.llms import Ollama
#from langchain_community.chat_models import ChatOllama
from langchain_ollama import ChatOllama
#from langchain_core.tools import tool
#from langchain.agents import initialize_agent, AgentType
#from langchain_ollama import OllamaEmbeddings

from langchain.prompts import PromptTemplate
import os
#from langgraph.prebuilt import ToolNode
#from typing import Literal
#from langgraph.graph import END
#from langgraph.graph import START, END
#from langgraph.graph import MessagesState, StateGraph
#from langchain_core.prompts import PromptTemplate
import re
import json
from langchain.schema import Document
from pathlib import Path

# model cell

embeddings = OllamaEmbeddings(
    model="bge-m3"
)

llm = ChatOllama(
    model="qwen3:4b"
)

persist_directory = "./fastapi-client/chroma_db"
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
        inner = re.search(r"<output>(.*)</output>", picked, flags=re.DOTALL | re.IGNORECASE).group(1).strip()
        return json.loads(inner) 
    else:
        return picked

def load_or_build_vector_store():
    print("[DEBUG] cwd       =", Path.cwd())
    if os.path.exists('./fastapi-client/chroma_db') and len(os.listdir('./fastapi-client/chroma_db')) > 0:
        #기존 벡터 DB 가 존재할 경우.
        print("Vector DB 존재. 불러오기 시작.")
        collection_name = 'requirements_list'
        persist_directory = "./fastapi-client/chroma_db"
        
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
        file_path = "docs/RFP_requirements.md"

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()


        doc_parse_prompt = PromptTemplate.from_template(r"""
            당신은 SI 프로젝트 요구사항 정의서를 읽고, 개발자가 바로 사용할 수 있는 JSON 체크리스트로 변환하는 도우미입니다.
            입력으로 SFR 섹션 하나(마크다운)가 주어집니다.

            [출력 형식 규칙]
            1) 출력은 오직 JSON만. 앞/뒤 설명, 마크다운, 코드펜스 금지.
            2) 스키마는 아래와 동일해야 함:
            {{
            "요구사항ID": "<SFR-XXX>",
            "기능명": "<한 줄 요약>",
            "구현항목": [
                {{
                "하위ID": "<SFR-XXX-01>",
                "내용": "<구현해야 할 기능>",
                "구현시참고사항": "<개발 시 유의/맥락 1문장>"
                }}
            ]
            }}
            3) "하위ID"는 요구사항ID에서 파생: <SFR-XXX-01>, <SFR-XXX-02> … 두 자리 증가.
            4) "내용"은 입력의 '소분류'와 그 하위 불릿들을 분석해, 실행 가능 문장으로 간결(최대 30자)하게. 핵심 동사를 앞에 둔다.
            - 예: "엑셀 업로드 통한 대량 과정 등록", "과정 리스트 조회 및 수료 처리"
            5) "구현시참고사항"은 의도/운영 관점에서 1문장(최대 40자)으로 요약.
            - 정책, 예외, 대량처리, 변경반영, 추적성 등의 키워드를 적절히 반영하되 사실 확장/추측 금지.
            6) 근거문서/비고/메타 정보는 JSON에 포함하지 않는다.
            7) 입력에 없는 기능은 생성하지 않는다(할루시네이션 금지). 한글만 사용하고, 따옴표는 ASCII(")만 사용.

            [입력 섹션]

            {section}

            위 섹션을 단일 JSON으로 변환하시오.
                                                        
            모든 출력은 <output> 태그 안에 담아서 추출하기 좋게 정리해주세요.
            출력 예시 : 
            <outout>
                당신이 생각한 모든 출력
            </output>
        """)

        msg = doc_parse_prompt.format(section=content)
        response = llm.invoke(msg)

        
        text = response.content 
        only_output_block = extract_output_after_removing_think(text) 
        parsed_json = extract_output_after_removing_think(text, return_json=True)

        vector_db_items = []
        for idx1, sfr in enumerate(parsed_json):
            for idx2, detail_sfr in enumerate(sfr['구현항목']):
                req_id = parsed_json[idx1]['요구사항ID']
                sub_item_id = detail_sfr['하위ID']
                str_detail_sft = json.dumps(detail_sfr)
                # print(req_id)
                # print(sub_item_id)
                # print(detail_sfr)
                doc = Document(page_content=str_detail_sft,metadata={"source": req_id, "list_name": sub_item_id, "idx": idx2})
                vector_db_items.append(doc)

        # 3. 벡터 스토어 생성
        persist_directory = "./fastapi-client/chroma_db"
        collection_name = 'requirements_list'
        vector_store = Chroma.from_documents(
            documents=vector_db_items, 
            embedding=embeddings, 
            persist_directory=persist_directory,
            collection_name=collection_name    
        )
        print("Vector DB 생성 완료.")

        return vector_store, embeddings


