from typing import List, Tuple
import numpy as np
from langchain.schema import Document
from langchain_community.embeddings import OllamaEmbeddings
from typing import List
from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

# 필요시 base_url, num_ctx 등 옵션 추가 가능
def get_ollama_bge_m3(model: str = "bge-m3", base_url: str | None = None) -> OllamaEmbeddings:
    if base_url:
        return OllamaEmbeddings(model=model, base_url=base_url)
    return OllamaEmbeddings(model=model)

# 간단 캐시(선택)
_EMBED_CACHE: dict[str, np.ndarray] = {}

# OllamaEmbeddings 인스턴스를 전역으로 한 번만 생성
_GLOBAL_EMBEDDER = get_ollama_bge_m3()

def _embed(texts: List[str]) -> np.ndarray:
    vecs = _GLOBAL_EMBEDDER.embed_documents(texts)
    return np.asarray(vecs, dtype=np.float32)

def _embed_query(q: str) -> np.ndarray:
    if q in _EMBED_CACHE:
        return _EMBED_CACHE[q]
    emb = get_ollama_bge_m3()
    v = np.asarray(_GLOBAL_EMBEDDER.embed_query(q), dtype=np.float32)
    _EMBED_CACHE[q] = v
    return v

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # a: [D], b: [B, D]
    a_norm = a / (np.linalg.norm(a) + 1e-8)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-8)
    return b_norm @ a_norm  # [B]

def ollama_bge_rerank(query: str, docs: List[Document], top_n: int = 3) -> List[Tuple[Document, float]]:
    if not docs:
        return []
    passages = [d.page_content for d in docs]

    qv = _embed_query(query)
    dv = _embed(passages)             # 후보 문서만 임베딩 → 비용 낮음
    sims = _cosine_sim(qv, dv).tolist()

    ranked = sorted(zip(docs, sims), key=lambda x: x[1], reverse=True)
    return ranked[:min(top_n, len(ranked))]


class OllamaBGERerankRetriever(BaseRetriever, BaseModel):
    base_retriever: BaseRetriever = Field(...)
    k_init: int = Field(default=30)
    k_final: int = Field(default=3)

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # 초기 후보
        candidates: List[Document] = self.base_retriever.get_relevant_documents(query=query, k=self.k_init)
        # 임베딩 기반 재정렬
        ranked = ollama_bge_rerank(query, candidates, top_n=self.k_final)
        return [doc for doc, _ in ranked]

    async def _aget_relevant_documents(self, query: str) -> List[Document]:
        return self._get_relevant_documents(query)