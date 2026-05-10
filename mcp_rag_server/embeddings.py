# Design Ref: §3.3 — BGE-m3-ko 지연 로딩, MPS GPU 활용, 쿼리 prefix
import logging

import numpy as np

from mcp_rag_server.config import Config

logger = logging.getLogger(__name__)


class EmbeddingEngine:
    def __init__(self, config: Config):
        self.model = None
        self.config = config

    def _ensure_loaded(self):
        """지연 로딩: 첫 호출 시에만 모델 로드 (~2GB, ~10초)"""
        if self.model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("임베딩 모델 로딩 중: %s", self.config.embedding_model)
            try:
                self.model = SentenceTransformer(
                    self.config.embedding_model,
                    device="mps",
                )
            except Exception:
                logger.warning("MPS 사용 불가, CPU로 폴백")
                self.model = SentenceTransformer(
                    self.config.embedding_model,
                    device="cpu",
                )
            logger.info("임베딩 모델 로딩 완료")

    def encode(self, texts: list[str]) -> np.ndarray:
        """텍스트 리스트 → 벡터 배열 (batch 처리)"""
        self._ensure_loaded()
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )

    def encode_query(self, query: str) -> np.ndarray:
        """단일 쿼리 → 벡터 (검색용, BGE prefix 추가)"""
        self._ensure_loaded()
        prefixed = f"query: {query}"
        return self.model.encode(
            [prefixed],
            normalize_embeddings=True,
        )[0]
