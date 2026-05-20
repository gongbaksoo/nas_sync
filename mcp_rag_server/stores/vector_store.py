# Design Ref: §3.10 — LanceDB 래퍼, 벡터 CRUD, 시맨틱 검색
import logging

import lancedb
import numpy as np
import pyarrow as pa

from mcp_rag_server.config import Config

logger = logging.getLogger(__name__)


class VectorStore:
    TABLE_NAME = "documents"

    def __init__(self, config: Config):
        self.config = config
        config.ensure_dirs()
        self.db = lancedb.connect(str(config.vector_db_path))
        self._ensure_table()

    def _ensure_table(self):
        """테이블이 없으면 스키마로 생성"""
        if self.TABLE_NAME not in self.db.table_names():
            schema = pa.schema([
                pa.field("vector", pa.list_(pa.float32(), self.config.embedding_dimension)),
                pa.field("text", pa.utf8()),
                pa.field("source_file", pa.utf8()),
                pa.field("file_name", pa.utf8()),
                pa.field("file_type", pa.utf8()),
                pa.field("chunk_id", pa.utf8()),
                pa.field("page_or_sheet", pa.utf8()),
                pa.field("date_created", pa.utf8()),
                pa.field("date_indexed", pa.utf8()),
                pa.field("size_bytes", pa.int64()),
                pa.field("language", pa.utf8()),
            ])
            self.db.create_table(self.TABLE_NAME, schema=schema)
            logger.info("LanceDB 테이블 '%s' 생성 완료", self.TABLE_NAME)

    def upsert(self, chunks: list[dict], vectors: np.ndarray):
        """청크 + 벡터 저장 (동일 소스 파일 청크 교체)"""
        table = self.db.open_table(self.TABLE_NAME)

        if chunks:
            source = chunks[0].get("source_file", "")
            try:
                table.delete(f"source_file = '{source}'")
            except Exception:
                pass

        records = []
        for i, chunk in enumerate(chunks):
            records.append({
                "vector": vectors[i].tolist(),
                "text": chunk.get("text", ""),
                "source_file": chunk.get("source_file", ""),
                "file_name": chunk.get("file_name", ""),
                "file_type": chunk.get("file_type", ""),
                "chunk_id": chunk.get("chunk_id", ""),
                "page_or_sheet": chunk.get("page_or_sheet", ""),
                "date_created": chunk.get("date_created", ""),
                "date_indexed": chunk.get("date_indexed", ""),
                "size_bytes": chunk.get("size_bytes", 0),
                "language": chunk.get("language", "ko"),
            })

        if records:
            batch_size = 1000
            total = len(records)
            for start in range(0, total, batch_size):
                end = min(start + batch_size, total)
                table.add(records[start:end])
                logger.info(
                    "청크 저장 진행: %d/%d (소스: %s)",
                    end,
                    total,
                    chunks[0].get("file_name", ""),
                )
            logger.info("%d 청크 저장 완료 (소스: %s)", total, chunks[0].get("file_name", ""))

    def search(self, query_vector: np.ndarray, top_k: int = 5,
               filters: dict | None = None) -> list[dict]:
        """벡터 유사도 검색"""
        table = self.db.open_table(self.TABLE_NAME)

        try:
            if table.count_rows() == 0:
                return []
        except Exception:
            return []

        query = table.search(query_vector.tolist()).limit(top_k)

        if filters and "file_type" in filters:
            query = query.where(f"file_type = '{filters['file_type']}'")

        results = query.to_list()
        for r in results:
            r["score"] = 1 - r.get("_distance", 1)
        return results

    def get_by_source(self, source_file: str, page: int | None = None,
                      sheet: str | None = None) -> list[dict]:
        """소스 파일로 청크 조회"""
        table = self.db.open_table(self.TABLE_NAME)
        condition = f"source_file = '{source_file}'"
        if sheet:
            condition += f" AND page_or_sheet = '{sheet}'"

        try:
            return table.search().where(condition).limit(100).to_list()
        except Exception:
            return []

    def get_stats(self) -> dict:
        """벡터 스토어 통계"""
        try:
            table = self.db.open_table(self.TABLE_NAME)
            total = table.count_rows()
            return {
                "total_chunks": total,
                "table": self.TABLE_NAME,
                "path": str(self.config.vector_db_path),
            }
        except Exception:
            return {"total_chunks": 0, "table": self.TABLE_NAME}
