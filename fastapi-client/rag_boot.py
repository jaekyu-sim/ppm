# 가상환경 실행 : .\.venv\Scripts\activate.ps1

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.embeddings import OllamaEmbeddings
from langchain_chroma import Chroma
#from langchain_community.llms import Ollama
#from langchain_community.chat_models import ChatOllama
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain.agents import initialize_agent, AgentType
#from langchain_ollama import OllamaEmbeddings
import os
from langgraph.prebuilt import ToolNode
from typing import Literal
#from langgraph.graph import END
from langgraph.graph import START, END
from langgraph.graph import MessagesState, StateGraph
from langchain_core.prompts import PromptTemplate
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


def load_or_build_vector_store():
    print("[DEBUG] cwd       =", Path.cwd())
    if os.path.exists('./fastapi-client/chroma_db') and len(os.listdir('./fastapi-client/chroma_db')) > 0:
        #기존 벡터 DB 가 존재할 경우.
        print("Vector DB 존재. 불러오기 시작.")
        
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
        loader = TextLoader("./fastapi-client/docs/RFP_requirements.md", encoding="utf-8")
        documents = loader.load()

        # 2. 문서 나누기
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        splits = text_splitter.split_documents(documents)
        print(f"Chroma DB에 {len(splits)}개의 문서를 임베딩하여 저장 완료.")

        # 3. 벡터 스토어 생성
        vector_store = Chroma.from_documents(
            documents=splits, 
            embedding=embeddings, 
            persist_directory=persist_directory,
            collection_name=collection_name    
        )
        print("Vector DB 생성 완료.")

        return vector_store, embeddings


