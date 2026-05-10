# Design Ref: §3.5 — 벡터/키워드/SQL/하이브리드 검색, 결과 정규화
import logging
import re

from mcp_rag_server.config import Config
from mcp_rag_server.embeddings import EmbeddingEngine
from mcp_rag_server.stores.vector_store import VectorStore
from mcp_rag_server.stores.sql_store import SqlStore
from mcp_rag_server.utils.korean import KoreanProcessor

logger = logging.getLogger(__name__)


class Searcher:
    def __init__(self, config: Config, embeddings: EmbeddingEngine,
                 vector_store: VectorStore, sql_store: SqlStore):
        self.config = config
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.sql_store = sql_store
        self.korean = KoreanProcessor()

    async def search_documents(self, query: str, top_k: int = 5,
                               file_type: str | None = None) -> list[dict]:
        """시맨틱 검색 (벡터 유사도 기반)

        Plan SC: 자연어로 NAS 파일 검색 가능
        """
        query_vector = self.embeddings.encode_query(query)

        filters = {}
        if file_type:
            filters["file_type"] = file_type

        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            filters=filters,
        )

        return [self._format_result(r) for r in results]

    async def search_excel(self, query: str, sheet_name: str | None = None,
                           sql_filter: str | None = None) -> list[dict]:
        """Excel 하이브리드 검색 (시맨틱 + SQL)

        Plan SC: Excel 데이터에 대해 수치 질의 응답 가능
        """
        results = []

        # 시맨틱 검색
        query_vector = self.embeddings.encode_query(query)
        vector_results = self.vector_store.search(
            query_vector=query_vector,
            top_k=self.config.default_top_k,
            filters={"file_type": "excel"},
        )
        results.extend(vector_results)

        # 명시적 SQL 필터
        if sql_filter:
            sql_results = self.sql_store.query(sql_filter, sheet_name)
            results.extend(sql_results)

        # 자연어에서 수치 조건 자동 추출
        if not sql_filter:
            extracted = self._extract_numeric_condition(query)
            if extracted:
                sql_results = self.sql_store.query(extracted, sheet_name)
                results.extend(sql_results)

        return self._deduplicate_and_rank(results)

    async def search_receipts(self, query: str, date_range: str | None = None,
                              amount_range: str | None = None) -> list[dict]:
        """영수증/이미지 OCR 검색

        Plan SC: 영수증 이미지에서 OCR 기반 검색 가능
        """
        query_vector = self.embeddings.encode_query(query)
        filters = {"file_type": "image"}

        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=self.config.default_top_k,
            filters=filters,
        )

        # 날짜/금액 필터 (메타데이터 기반 후처리)
        if date_range or amount_range:
            results = self._filter_by_metadata(results, date_range, amount_range)

        return [self._format_result(r) for r in results]

    async def get_file_content(self, file_path: str,
                               page: int | None = None,
                               sheet: str | None = None) -> dict:
        """인덱싱된 파일의 원본 내용 조회"""
        chunks = self.vector_store.get_by_source(file_path, page=page, sheet=sheet)
        if not chunks:
            return {"status": "not_found", "file": file_path}

        return {
            "status": "found",
            "file": file_path,
            "file_name": chunks[0].get("file_name", ""),
            "content": "\n\n".join(c.get("text", "") for c in chunks),
            "chunks": len(chunks),
        }

    def _format_result(self, raw: dict) -> dict:
        """검색 결과 정규화 — 불필요한 필드(vector 등) 제거"""
        return {
            "text": raw.get("text", ""),
            "score": round(raw.get("score", 0.0), 4),
            "source_file": raw.get("source_file", ""),
            "file_name": raw.get("file_name", ""),
            "file_type": raw.get("file_type", ""),
            "page_or_sheet": raw.get("page_or_sheet", ""),
            "chunk_id": raw.get("chunk_id", ""),
        }

    def _extract_numeric_condition(self, query: str) -> str | None:
        """자연어에서 SQL WHERE 조건 추출 (패턴 매칭)

        예: "매출 100만원 이상" -> 매출 >= 1000000
        """
        # "N만원 이상/이하" 패턴
        match = re.search(r"(\w+)\s+(\d+)\s*만\s*원?\s*(이상|초과)", query)
        if match:
            col, val, op = match.groups()
            multiplied = int(val) * 10000
            operator = ">=" if op == "이상" else ">"
            return f'"{col}" {operator} {multiplied}'

        match = re.search(r"(\w+)\s+(\d+)\s*만\s*원?\s*(이하|미만)", query)
        if match:
            col, val, op = match.groups()
            multiplied = int(val) * 10000
            operator = "<=" if op == "이하" else "<"
            return f'"{col}" {operator} {multiplied}'

        # "N 이상/이하" (만원 없이)
        match = re.search(r"(\w+)\s+(\d+)\s*(이상|초과|이하|미만)", query)
        if match:
            col, val, op = match.groups()
            operators = {"이상": ">=", "초과": ">", "이하": "<=", "미만": "<"}
            return f'"{col}" {operators[op]} {val}'

        return None

    def _deduplicate_and_rank(self, results: list[dict]) -> list[dict]:
        """중복 제거 + 점수 기반 재순위"""
        seen = set()
        unique = []
        for r in results:
            key = r.get("chunk_id", r.get("text", "")[:50])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        unique.sort(key=lambda x: x.get("score", 0), reverse=True)
        return [self._format_result(r) for r in unique[:self.config.default_top_k]]

    def _filter_by_metadata(self, results: list[dict], date_range: str | None,
                            amount_range: str | None) -> list[dict]:
        """메타데이터 기반 후처리 필터 (Phase 2에서 고도화)"""
        # 현재는 필터 없이 반환 — 이미지 파서가 구현되면 메타데이터 활용
        return results
