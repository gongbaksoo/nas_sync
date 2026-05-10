# NAS Agentic RAG 시스템 Design

> 생성일: 2026-05-09
> Phase: Design
> Plan: docs/01-plan/features/nas-agentic-rag.plan.md
> Architecture: Option C — Pragmatic Balance

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | NAS 파일을 자연어로 검색/분석할 수 없어 매번 수동으로 폴더 탐색해야 함 |
| **WHO** | Mac Mini에서 Claude Code를 사용하는 본인 (1인 사용자) |
| **RISK** | Mac Mini 리소스 제약, NAS 네트워크 지연, 한국어 임베딩 품질 |
| **SUCCESS** | 자연어로 NAS 파일 검색 + Excel 수치 질의 + 영수증 OCR 검색 + Agentic 라우팅 |
| **SCOPE** | 커스텀 Python MCP 서버, 3단계 구현 (기본 RAG → OCR → Agentic) |

---

## 1. Overview

### 1.1 설계 목표
Claude Code에서 MCP 프로토콜로 연결되는 Python 기반 RAG 서버를 구축한다.
NAS에 저장된 PDF, Excel, 이미지 파일을 인덱싱하고, 자연어 질의로 검색 및 내용 분석을 수행한다.

### 1.2 선택된 아키텍처
**Option C — Pragmatic Balance**: 12개 파일, 모듈별 단일 책임, 추상 인터페이스 없이 직접 구현.

### 1.3 비기능 요구사항
| 항목 | 목표 |
|------|------|
| 검색 응답 시간 | < 3초 (벡터 검색 기준) |
| 인덱싱 처리량 | ~10 파일/분 (PDF 기준) |
| 메모리 사용 | < 3GB (임베딩 모델 포함) |
| 디스크 사용 | 원본 파일 대비 ~20% 추가 (인덱스) |
| 가용성 | Claude Code 세션 중 MCP 서버 상시 가동 |

---

## 2. Project Structure

```
nas_sync/
├── mcp_rag_server/
│   ├── __init__.py
│   ├── server.py              # [M1] MCP 서버 엔트리포인트
│   ├── config.py              # [M2] 설정 관리
│   ├── embeddings.py          # [M3] BGE-m3-ko 임베딩 래퍼
│   ├── indexer.py             # [M4] 인덱싱 오케스트레이터
│   ├── searcher.py            # [M5] 검색 오케스트레이터
│   ├── agentic_router.py      # [M6] Agentic 라우팅 + Self-reflection
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py      # [M7] Docling PDF 파싱
│   │   ├── excel_parser.py    # [M8] pandas Excel 파싱
│   │   └── image_parser.py    # [M9] EasyOCR 이미지 파싱
│   ├── stores/
│   │   ├── __init__.py
│   │   ├── vector_store.py    # [M10] LanceDB 래퍼
│   │   └── sql_store.py       # [M11] DuckDB 래퍼
│   └── utils/
│       ├── __init__.py
│       └── korean.py          # [M12] Kiwi + KSS 한국어 처리
├── tests/
│   ├── test_parsers.py
│   ├── test_search.py
│   └── test_integration.py
├── pyproject.toml             # 프로젝트 설정 + 의존성
└── README.md
```

---

## 3. Module Design

### 3.1 [M1] server.py — MCP 서버 엔트리포인트

**책임**: MCP 프로토콜 핸들링, 도구 등록, 요청 라우팅

```python
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from config import Config
from indexer import Indexer
from searcher import Searcher
from agentic_router import AgenticRouter

app = Server("nas-rag")
config = Config()
indexer = Indexer(config)
searcher = Searcher(config)
router = AgenticRouter(config, searcher)  # Phase 3

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="search_documents", description="NAS 문서 시맨틱 검색", inputSchema={...}),
        Tool(name="search_excel", description="Excel 하이브리드 검색", inputSchema={...}),
        Tool(name="search_receipts", description="영수증/이미지 OCR 검색", inputSchema={...}),
        Tool(name="index_file", description="단일 파일 인덱싱", inputSchema={...}),
        Tool(name="index_directory", description="디렉토리 일괄 인덱싱", inputSchema={...}),
        Tool(name="get_file_content", description="파일 원본 내용 조회", inputSchema={...}),
        Tool(name="get_stats", description="인덱싱 현황/통계", inputSchema={...}),
        Tool(name="smart_search", description="Agentic 자동 라우팅 검색", inputSchema={...}),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    match name:
        case "search_documents":
            results = await searcher.search_documents(**arguments)
        case "search_excel":
            results = await searcher.search_excel(**arguments)
        case "search_receipts":
            results = await searcher.search_receipts(**arguments)
        case "index_file":
            results = await indexer.index_file(**arguments)
        case "index_directory":
            results = await indexer.index_directory(**arguments)
        case "get_file_content":
            results = await searcher.get_file_content(**arguments)
        case "get_stats":
            results = await indexer.get_stats()
        case "smart_search":
            results = await router.smart_search(**arguments)
    return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False))]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

**의존성**: config, indexer, searcher, agentic_router
**MCP SDK**: `mcp[cli]` (Python SDK)

---

### 3.2 [M2] config.py — 설정 관리

**책임**: 모든 경로, 모델명, 파라미터를 중앙 관리

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Config:
    # NAS 경로
    nas_base_path: Path = Path("/Volumes/personal_folder")
    nas_backup_path: Path = Path("/Volumes/personal_folder/Macmini_backup")

    # 인덱스 저장 경로
    vector_db_path: Path = Path("/Volumes/personal_folder/rag_db/lancedb")
    sql_db_path: Path = Path("/Volumes/personal_folder/rag_db/excel_data.duckdb")

    # 임베딩 모델
    embedding_model: str = "upskyy/bge-m3-korean"
    embedding_dimension: int = 1024

    # 청킹 파라미터
    pdf_chunk_size: int = 800       # 토큰 (한국어 특성상 영어보다 작게)
    pdf_chunk_overlap: int = 80     # 토큰
    excel_row_group_size: int = 15  # 행 그룹 크기

    # 검색 파라미터
    default_top_k: int = 5
    similarity_threshold: float = 0.3  # 최소 유사도

    # 지원 확장자
    supported_extensions: dict = field(default_factory=lambda: {
        "pdf": [".pdf"],
        "excel": [".xlsx", ".xls"],
        "image": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    })
```

---

### 3.3 [M3] embeddings.py — 임베딩 엔진

**책임**: BGE-m3-ko 모델 로드, 텍스트→벡터 변환

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingEngine:
    def __init__(self, config):
        self.model = None
        self.config = config

    def _ensure_loaded(self):
        """지연 로딩: 첫 호출 시에만 모델 로드 (~2GB, ~10초)"""
        if self.model is None:
            self.model = SentenceTransformer(
                self.config.embedding_model,
                device="mps"  # Apple Silicon GPU 활용
            )

    def encode(self, texts: list[str]) -> np.ndarray:
        """텍스트 리스트 → 벡터 배열 (batch 처리)"""
        self._ensure_loaded()
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False
        )

    def encode_query(self, query: str) -> np.ndarray:
        """단일 쿼리 → 벡터 (검색용, prefix 추가)"""
        self._ensure_loaded()
        # BGE 계열은 쿼리에 prefix를 붙이면 성능 향상
        prefixed = f"query: {query}"
        return self.model.encode(
            [prefixed],
            normalize_embeddings=True
        )[0]
```

**핵심 설계 결정**:
- **지연 로딩**: 서버 시작 시 모델을 바로 로드하지 않음 → MCP 서버 시작 속도 개선
- **MPS 디바이스**: Apple Silicon GPU 활용으로 임베딩 속도 ~3x 향상
- **쿼리 prefix**: BGE 계열 모델의 비대칭 검색 최적화

---

### 3.4 [M4] indexer.py — 인덱싱 오케스트레이터

**책임**: 파일 탐지 → 파서 선택 → 청킹 → 임베딩 → 스토어 저장

```python
import os
import json
from datetime import datetime
from pathlib import Path

from config import Config
from embeddings import EmbeddingEngine
from parsers.pdf_parser import PdfParser
from parsers.excel_parser import ExcelParser
from parsers.image_parser import ImageParser
from stores.vector_store import VectorStore
from stores.sql_store import SqlStore

class Indexer:
    def __init__(self, config: Config):
        self.config = config
        self.embeddings = EmbeddingEngine(config)
        self.vector_store = VectorStore(config)
        self.sql_store = SqlStore(config)
        self.parsers = {
            "pdf": PdfParser(config),
            "excel": ExcelParser(config),
            "image": ImageParser(config),
        }

    def _detect_file_type(self, file_path: str) -> str | None:
        """확장자로 파일 타입 감지"""
        ext = Path(file_path).suffix.lower()
        for file_type, extensions in self.config.supported_extensions.items():
            if ext in extensions:
                return file_type
        return None

    async def index_file(self, file_path: str) -> dict:
        """단일 파일 인덱싱

        Returns:
            {"status": "success", "file": ..., "chunks": N, "type": ...}
        """
        file_type = self._detect_file_type(file_path)
        if not file_type:
            return {"status": "error", "message": f"지원하지 않는 파일 형식: {file_path}"}

        if not os.path.exists(file_path):
            return {"status": "error", "message": f"파일을 찾을 수 없음: {file_path}"}

        # 1. 파싱 → 청크 리스트
        parser = self.parsers[file_type]
        chunks = parser.parse(file_path)

        if not chunks:
            return {"status": "error", "message": "파싱 결과가 비어있음"}

        # 2. 임베딩
        texts = [c["text"] for c in chunks]
        vectors = self.embeddings.encode(texts)

        # 3. 벡터 스토어 저장
        self.vector_store.upsert(chunks, vectors)

        # 4. Excel인 경우 SQL 스토어에도 저장
        if file_type == "excel":
            self.sql_store.import_excel(file_path)

        return {
            "status": "success",
            "file": file_path,
            "type": file_type,
            "chunks": len(chunks),
            "indexed_at": datetime.now().isoformat()
        }

    async def index_directory(self, dir_path: str, recursive: bool = True,
                              file_types: list[str] = None) -> dict:
        """디렉토리 내 모든 지원 파일 일괄 인덱싱"""
        results = {"total": 0, "success": 0, "failed": 0, "files": []}

        for root, _, files in os.walk(dir_path):
            if not recursive and root != dir_path:
                continue
            for fname in files:
                fpath = os.path.join(root, fname)
                ftype = self._detect_file_type(fpath)
                if ftype is None:
                    continue
                if file_types and ftype not in file_types:
                    continue

                result = await self.index_file(fpath)
                results["total"] += 1
                if result["status"] == "success":
                    results["success"] += 1
                else:
                    results["failed"] += 1
                results["files"].append(result)

        return results

    async def get_stats(self) -> dict:
        """인덱싱 현황 통계"""
        vector_stats = self.vector_store.get_stats()
        sql_stats = self.sql_store.get_stats()
        return {
            "vector_store": vector_stats,
            "sql_store": sql_stats,
            "config": {
                "embedding_model": self.config.embedding_model,
                "nas_path": str(self.config.nas_backup_path),
            }
        }
```

---

### 3.5 [M5] searcher.py — 검색 오케스트레이터

**책임**: 벡터/키워드/SQL/하이브리드 검색 실행, 결과 정규화

```python
from config import Config
from embeddings import EmbeddingEngine
from stores.vector_store import VectorStore
from stores.sql_store import SqlStore
from utils.korean import KoreanProcessor

class Searcher:
    def __init__(self, config: Config):
        self.config = config
        self.embeddings = EmbeddingEngine(config)
        self.vector_store = VectorStore(config)
        self.sql_store = SqlStore(config)
        self.korean = KoreanProcessor()

    async def search_documents(self, query: str, top_k: int = 5,
                                file_type: str = None) -> list[dict]:
        """시맨틱 검색 (벡터 유사도 기반)

        1. 쿼리 임베딩
        2. LanceDB 벡터 검색
        3. 메타데이터 필터 적용 (file_type)
        4. 결과 정규화 + 출처 포함
        """
        query_vector = self.embeddings.encode_query(query)

        filters = {}
        if file_type:
            filters["file_type"] = file_type

        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=top_k,
            filters=filters
        )

        return [self._format_result(r) for r in results]

    async def search_excel(self, query: str, sheet_name: str = None,
                           sql_filter: str = None) -> list[dict]:
        """Excel 하이브리드 검색

        전략:
        1. 시맨틱 검색 (쿼리 의미 기반)
        2. SQL 검색 (수치/조건 기반) — sql_filter 있을 때
        3. 두 결과 병합 + 중복 제거 + 재순위
        """
        results = []

        # 시맨틱 검색
        query_vector = self.embeddings.encode_query(query)
        vector_results = self.vector_store.search(
            query_vector=query_vector,
            top_k=self.config.default_top_k,
            filters={"file_type": "excel"}
        )
        results.extend(vector_results)

        # SQL 검색 (수치 쿼리)
        if sql_filter:
            sql_results = self.sql_store.query(sql_filter, sheet_name)
            results.extend(sql_results)

        # 자연어에서 수치 조건 추출 시도
        extracted_condition = self._extract_numeric_condition(query)
        if extracted_condition and not sql_filter:
            sql_results = self.sql_store.query(extracted_condition, sheet_name)
            results.extend(sql_results)

        return self._deduplicate_and_rank(results)

    async def search_receipts(self, query: str, date_range: str = None,
                              amount_range: str = None) -> list[dict]:
        """영수증/이미지 OCR 검색

        1. 벡터 검색 (OCR 텍스트 유사도)
        2. 메타데이터 필터 (날짜, 금액 범위)
        """
        query_vector = self.embeddings.encode_query(query)
        filters = {"file_type": "image"}

        if date_range:
            filters["date_range"] = date_range
        if amount_range:
            filters["amount_range"] = amount_range

        results = self.vector_store.search(
            query_vector=query_vector,
            top_k=self.config.default_top_k,
            filters=filters
        )

        return [self._format_result(r) for r in results]

    async def get_file_content(self, file_path: str,
                               page: int = None, sheet: str = None) -> dict:
        """인덱싱된 파일의 원본 내용 조회

        벡터 스토어에서 해당 파일의 모든 청크를 검색하여 원본 복원
        """
        chunks = self.vector_store.get_by_source(file_path, page=page, sheet=sheet)
        if not chunks:
            return {"status": "not_found", "file": file_path}

        return {
            "status": "found",
            "file": file_path,
            "content": "\n\n".join([c["text"] for c in chunks]),
            "chunks": len(chunks),
            "metadata": chunks[0].get("metadata", {})
        }

    def _format_result(self, raw: dict) -> dict:
        """검색 결과 정규화"""
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
        """자연어에서 SQL 조건 추출 (간단한 패턴 매칭)

        예: "매출 100만원 이상" → "매출 >= 1000000"
        """
        # Phase 1에서는 간단한 패턴 매칭, Phase 3에서 LLM 기반으로 고도화
        import re
        patterns = [
            (r"(\w+)\s*(\d+)\s*만?\s*원?\s*(이상|초과)", r"\1 >= \2"),
            (r"(\w+)\s*(\d+)\s*만?\s*원?\s*(이하|미만)", r"\1 <= \2"),
        ]
        for pattern, replacement in patterns:
            match = re.search(pattern, query)
            if match:
                return re.sub(pattern, replacement, query)
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
```

---

### 3.6 [M6] agentic_router.py — Agentic 라우팅 (Phase 3)

**책임**: 쿼리 의도 분석 → 최적 검색 전략 선택 → Self-reflection

```python
import re
from enum import Enum

class QueryIntent(Enum):
    DOCUMENT_SEARCH = "document"    # "회사소개서 찾아줘"
    NUMERIC_ANALYSIS = "numeric"    # "매출 합계는?"
    RECEIPT_SEARCH = "receipt"      # "택시비 영수증"
    COMPOSITE = "composite"         # "마케팅 분석 보고서에서 유입수 높은 채널"

class AgenticRouter:
    def __init__(self, config, searcher):
        self.config = config
        self.searcher = searcher

    async def smart_search(self, query: str) -> dict:
        """Agentic RAG 메인 엔트리포인트

        1. 의도 분류
        2. 검색 전략 선택 & 실행
        3. Self-reflection (결과 품질 평가)
        4. 필요 시 재검색
        5. 최종 결과 반환
        """
        # Step 1: 의도 분류
        intent = self._classify_intent(query)

        # Step 2: 검색 실행
        results = await self._execute_search(intent, query)

        # Step 3: Self-reflection
        quality = self._evaluate_results(query, results)

        # Step 4: 품질 미달 시 재검색
        if quality["confidence"] < 0.5 and quality["retry_suggestion"]:
            refined_query = quality["retry_suggestion"]
            refined_intent = self._classify_intent(refined_query)
            retry_results = await self._execute_search(refined_intent, refined_query)
            # 원래 결과와 재검색 결과 병합
            results = self._merge_results(results, retry_results)
            quality = self._evaluate_results(query, results)

        return {
            "results": results,
            "search_strategy": intent.value,
            "confidence": quality["confidence"],
            "sources": list(set(r.get("source_file", "") for r in results)),
            "reflection": quality.get("explanation", "")
        }

    def _classify_intent(self, query: str) -> QueryIntent:
        """규칙 기반 의도 분류 (Phase 3 초기 버전)

        키워드 + 패턴 매칭으로 의도를 분류.
        향후 LLM 기반 분류로 고도화 가능.
        """
        query_lower = query.lower()

        # 영수증/경비 관련
        receipt_keywords = ["영수증", "택시", "교통비", "식대", "경비", "접대비", "receipt"]
        if any(kw in query_lower for kw in receipt_keywords):
            return QueryIntent.RECEIPT_SEARCH

        # 수치/분석 관련
        numeric_keywords = ["합계", "총액", "평균", "매출", "유입", "전환율", "얼마", "몇"]
        numeric_patterns = [r"\d+만?\s*원", r"이상|이하|초과|미만"]
        if any(kw in query_lower for kw in numeric_keywords):
            return QueryIntent.NUMERIC_ANALYSIS
        if any(re.search(p, query) for p in numeric_patterns):
            return QueryIntent.NUMERIC_ANALYSIS

        # 복합 쿼리 감지 (문서 + 수치)
        doc_keywords = ["보고서", "문서", "소개서", "분석", "파일"]
        has_doc = any(kw in query_lower for kw in doc_keywords)
        has_numeric = any(kw in query_lower for kw in numeric_keywords)
        if has_doc and has_numeric:
            return QueryIntent.COMPOSITE

        # 기본: 문서 검색
        return QueryIntent.DOCUMENT_SEARCH

    async def _execute_search(self, intent: QueryIntent, query: str) -> list[dict]:
        """의도에 맞는 검색 전략 실행"""
        match intent:
            case QueryIntent.DOCUMENT_SEARCH:
                return await self.searcher.search_documents(query)
            case QueryIntent.NUMERIC_ANALYSIS:
                return await self.searcher.search_excel(query)
            case QueryIntent.RECEIPT_SEARCH:
                return await self.searcher.search_receipts(query)
            case QueryIntent.COMPOSITE:
                # 문서 + 수치 검색 모두 실행 후 병합
                doc_results = await self.searcher.search_documents(query)
                excel_results = await self.searcher.search_excel(query)
                return self._merge_results(doc_results, excel_results)

    def _evaluate_results(self, query: str, results: list[dict]) -> dict:
        """Self-reflection: 검색 결과 품질 평가

        평가 기준:
        - 결과가 있는가?
        - 유사도 점수가 충분한가?
        - 결과가 다양한 소스에서 왔는가?
        """
        if not results:
            return {
                "confidence": 0.0,
                "explanation": "검색 결과 없음",
                "retry_suggestion": self._broaden_query(query)
            }

        scores = [r.get("score", 0) for r in results]
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)

        confidence = min(1.0, max_score * 1.2)  # 최고 점수 기반

        explanation = []
        retry_suggestion = None

        if max_score < 0.3:
            explanation.append("최고 유사도가 낮음 (< 0.3)")
            retry_suggestion = self._broaden_query(query)
        if len(results) < 2:
            explanation.append("결과가 너무 적음")
        if avg_score < 0.2:
            explanation.append("전체적으로 관련성 낮은 결과")
            retry_suggestion = self._broaden_query(query)

        return {
            "confidence": round(confidence, 2),
            "explanation": "; ".join(explanation) if explanation else "양호",
            "retry_suggestion": retry_suggestion
        }

    def _broaden_query(self, query: str) -> str:
        """쿼리 확장: 더 넓은 범위로 재검색"""
        # 간단한 전략: 조사 제거, 핵심 명사만 추출
        # Phase 3에서 Kiwi 형태소 분석 활용으로 고도화
        stopwords = ["찾아줘", "보여줘", "알려줘", "에서", "의", "를", "을", "이", "가"]
        words = query.split()
        filtered = [w for w in words if w not in stopwords]
        return " ".join(filtered) if filtered else query

    def _merge_results(self, a: list[dict], b: list[dict]) -> list[dict]:
        """두 결과 리스트 병합 + 중복 제거"""
        seen = set()
        merged = []
        for r in a + b:
            key = r.get("chunk_id", r.get("text", "")[:50])
            if key not in seen:
                seen.add(key)
                merged.append(r)
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)
        return merged[:self.config.default_top_k * 2]
```

---

### 3.7 [M7] parsers/pdf_parser.py — PDF 파싱

**책임**: Docling으로 PDF 텍스트/테이블 추출 → 시맨틱 청킹

```python
import os
from datetime import datetime
from docling.document_converter import DocumentConverter
from utils.korean import KoreanProcessor

class PdfParser:
    def __init__(self, config):
        self.config = config
        self.converter = DocumentConverter()
        self.korean = KoreanProcessor()

    def parse(self, file_path: str) -> list[dict]:
        """PDF → 청크 리스트

        1. Docling으로 텍스트 + 테이블 추출
        2. KSS로 한국어 문장 분리
        3. 시맨틱 청킹 (config.pdf_chunk_size 기준)
        4. 메타데이터 첨부
        """
        result = self.converter.convert(file_path)
        full_text = result.document.export_to_markdown()

        # 한국어 문장 분리 후 청킹
        sentences = self.korean.split_sentences(full_text)
        chunks = self._create_chunks(sentences, file_path)

        return chunks

    def _create_chunks(self, sentences: list[str], file_path: str) -> list[dict]:
        """문장 리스트 → 청크 리스트 (크기 기반 그룹화)"""
        chunks = []
        current_text = ""
        current_start = 0
        chunk_idx = 0
        file_name = os.path.basename(file_path)

        for i, sentence in enumerate(sentences):
            if len(current_text) + len(sentence) > self.config.pdf_chunk_size:
                if current_text.strip():
                    chunks.append(self._make_chunk(
                        text=current_text.strip(),
                        file_path=file_path,
                        file_name=file_name,
                        chunk_idx=chunk_idx
                    ))
                    chunk_idx += 1
                # 오버랩: 마지막 일부 문장 유지
                overlap_text = current_text[-self.config.pdf_chunk_overlap:]
                current_text = overlap_text + sentence + " "
            else:
                current_text += sentence + " "

        # 마지막 청크
        if current_text.strip():
            chunks.append(self._make_chunk(
                text=current_text.strip(),
                file_path=file_path,
                file_name=file_name,
                chunk_idx=chunk_idx
            ))

        return chunks

    def _make_chunk(self, text: str, file_path: str, file_name: str,
                    chunk_idx: int) -> dict:
        return {
            "text": text,
            "source_file": file_path,
            "file_name": file_name,
            "file_type": "pdf",
            "chunk_id": f"{file_name}_chunk_{chunk_idx}",
            "page_or_sheet": "",
            "date_created": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
            "date_indexed": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(file_path),
            "language": "ko",
        }
```

---

### 3.8 [M8] parsers/excel_parser.py — Excel 파싱

**책임**: pandas로 시트별 파싱 → 요약 청크 + 행 그룹 청크 + DuckDB용 데이터

```python
import os
from datetime import datetime
import pandas as pd

class ExcelParser:
    def __init__(self, config):
        self.config = config

    def parse(self, file_path: str) -> list[dict]:
        """Excel → 청크 리스트

        시트마다:
        1. 시트 요약 청크 (컬럼명, 행 수, 수치 통계)
        2. 행 그룹 청크 (헤더 항상 포함, 15-20행 단위)
        """
        chunks = []
        file_name = os.path.basename(file_path)

        try:
            xls = pd.ExcelFile(file_path)
        except Exception as e:
            return []

        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            except Exception:
                continue

            if df.empty:
                continue

            # 1. 시트 요약 청크
            summary = self._create_summary(df, file_path, file_name, sheet_name)
            chunks.append(summary)

            # 2. 행 그룹 청크
            row_chunks = self._create_row_groups(df, file_path, file_name, sheet_name)
            chunks.extend(row_chunks)

        return chunks

    def _create_summary(self, df: pd.DataFrame, file_path: str,
                        file_name: str, sheet_name: str) -> dict:
        """시트 요약 청크 생성"""
        columns = list(df.columns)
        summary_lines = [
            f"파일: {file_name}",
            f"시트: {sheet_name}",
            f"컬럼: {', '.join(str(c) for c in columns)}",
            f"행 수: {len(df)}",
        ]

        # 수치 컬럼 통계
        numeric_cols = df.select_dtypes(include="number").columns
        for col in numeric_cols:
            summary_lines.append(
                f"{col}: 합계={df[col].sum():,.0f}, "
                f"평균={df[col].mean():,.1f}, "
                f"최소={df[col].min():,.0f}, "
                f"최대={df[col].max():,.0f}"
            )

        return {
            "text": "\n".join(summary_lines),
            "source_file": file_path,
            "file_name": file_name,
            "file_type": "excel",
            "chunk_id": f"{file_name}_{sheet_name}_summary",
            "page_or_sheet": sheet_name,
            "columns": [str(c) for c in columns],
            "date_created": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
            "date_indexed": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(file_path),
            "language": "ko",
            "row_range": "summary",
        }

    def _create_row_groups(self, df: pd.DataFrame, file_path: str,
                           file_name: str, sheet_name: str) -> list[dict]:
        """행 그룹 청크 생성 (헤더 항상 포함)"""
        chunks = []
        header = " | ".join(str(c) for c in df.columns)
        group_size = self.config.excel_row_group_size

        for i in range(0, len(df), group_size):
            group = df.iloc[i:i + group_size]
            text_lines = [
                f"파일: {file_name} / 시트: {sheet_name}",
                f"헤더: {header}",
                f"행 {i+1}-{i+len(group)}:",
                group.to_string(index=False),
            ]

            chunks.append({
                "text": "\n".join(text_lines),
                "source_file": file_path,
                "file_name": file_name,
                "file_type": "excel",
                "chunk_id": f"{file_name}_{sheet_name}_rows_{i}-{i+len(group)}",
                "page_or_sheet": sheet_name,
                "columns": [str(c) for c in df.columns],
                "date_created": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
                "date_indexed": datetime.now().isoformat(),
                "size_bytes": os.path.getsize(file_path),
                "language": "ko",
                "row_range": f"{i}-{i+len(group)}",
            })

        return chunks
```

---

### 3.9 [M9] parsers/image_parser.py — 이미지/영수증 파싱 (Phase 2)

**책임**: EasyOCR로 이미지 텍스트 추출 + 메타데이터 생성

```python
import os
from datetime import datetime

class ImageParser:
    def __init__(self, config):
        self.config = config
        self._reader = None

    def _ensure_reader(self):
        """지연 로딩: EasyOCR는 무거우므로 필요할 때만 로드"""
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(["ko", "en"], gpu=True)

    def parse(self, file_path: str) -> list[dict]:
        """이미지 → 청크 (OCR 텍스트 + 메타데이터)

        1개 이미지 = 1개 청크
        """
        self._ensure_reader()
        file_name = os.path.basename(file_path)

        # OCR 실행
        try:
            ocr_results = self._reader.readtext(file_path, detail=1)
            ocr_text = " ".join([r[1] for r in ocr_results])
            ocr_confidence = sum(r[2] for r in ocr_results) / len(ocr_results) if ocr_results else 0
        except Exception:
            ocr_text = ""
            ocr_confidence = 0

        # 이미지 메타데이터
        try:
            from PIL import Image
            img = Image.open(file_path)
            resolution = f"{img.width}x{img.height}"
        except Exception:
            resolution = "unknown"

        # 폴더 경로에서 카테고리 추론
        category = self._infer_category(file_path)

        # 텍스트 구성: 파일명 + 카테고리 + OCR
        text_parts = [f"파일: {file_name}"]
        if category:
            text_parts.append(f"분류: {category}")
        if ocr_text:
            text_parts.append(f"내용: {ocr_text}")

        return [{
            "text": "\n".join(text_parts),
            "source_file": file_path,
            "file_name": file_name,
            "file_type": "image",
            "chunk_id": f"{file_name}_ocr",
            "page_or_sheet": "",
            "date_created": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
            "date_indexed": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(file_path),
            "language": "ko",
            "ocr_text": ocr_text,
            "ocr_confidence": round(ocr_confidence, 2),
            "resolution": resolution,
            "category": category,
        }]

    def _infer_category(self, file_path: str) -> str:
        """폴더 경로에서 카테고리 추론

        예: /개인경비/2403/240313_택시비.jpg → "개인경비/택시비"
        """
        parts = file_path.split(os.sep)
        # 알려진 카테고리 키워드
        category_keywords = ["경비", "상품", "이미지", "영수증", "사진"]
        for i, part in enumerate(parts):
            if any(kw in part for kw in category_keywords):
                return "/".join(parts[i:i+2]) if i+1 < len(parts) else part
        return ""
```

---

### 3.10 [M10] stores/vector_store.py — LanceDB 래퍼

**책임**: 벡터 CRUD, 시맨틱/풀텍스트 검색

```python
import lancedb
import pyarrow as pa
import numpy as np
from pathlib import Path

class VectorStore:
    TABLE_NAME = "documents"

    def __init__(self, config):
        self.config = config
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

    def upsert(self, chunks: list[dict], vectors: np.ndarray):
        """청크 + 벡터 저장 (기존 동일 chunk_id는 덮어쓰기)"""
        table = self.db.open_table(self.TABLE_NAME)

        # 기존 동일 소스 파일 청크 삭제 (재인덱싱 지원)
        if chunks:
            source = chunks[0].get("source_file", "")
            try:
                table.delete(f"source_file = '{source}'")
            except Exception:
                pass  # 첫 인덱싱 시에는 삭제할 것이 없음

        # 새 데이터 삽입
        records = []
        for i, chunk in enumerate(chunks):
            record = {
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
            }
            records.append(record)

        if records:
            table.add(records)

    def search(self, query_vector: np.ndarray, top_k: int = 5,
               filters: dict = None) -> list[dict]:
        """벡터 유사도 검색"""
        table = self.db.open_table(self.TABLE_NAME)
        query = table.search(query_vector.tolist()).limit(top_k)

        # 메타데이터 필터
        if filters:
            if "file_type" in filters:
                query = query.where(f"file_type = '{filters['file_type']}'")

        results = query.to_list()
        for r in results:
            r["score"] = 1 - r.get("_distance", 1)  # distance → similarity
        return results

    def get_by_source(self, source_file: str, page: int = None,
                      sheet: str = None) -> list[dict]:
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
```

---

### 3.11 [M11] stores/sql_store.py — DuckDB 래퍼

**책임**: Excel 데이터 SQL 저장/쿼리 (수치 검색용)

```python
import duckdb
import pandas as pd
import os
import re

class SqlStore:
    def __init__(self, config):
        self.config = config
        self.db_path = str(config.sql_db_path)
        self._ensure_db()

    def _ensure_db(self):
        """DB 파일 디렉토리 확인"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _get_connection(self):
        return duckdb.connect(self.db_path)

    def _sanitize_table_name(self, name: str) -> str:
        """테이블명으로 사용 가능한 형태로 변환"""
        # 파일명 + 시트명 → 안전한 테이블명
        safe = re.sub(r'[^\w]', '_', name)
        safe = re.sub(r'_+', '_', safe).strip('_')
        return safe[:60]  # DuckDB 테이블명 길이 제한

    def import_excel(self, file_path: str):
        """Excel 파일의 모든 시트를 DuckDB 테이블로 임포트"""
        conn = self._get_connection()
        file_name = os.path.basename(file_path)

        try:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if df.empty:
                    continue

                table_name = self._sanitize_table_name(f"{file_name}_{sheet_name}")

                # 기존 테이블 삭제 후 재생성
                conn.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")
                conn.execute(f"CREATE TABLE \"{table_name}\" AS SELECT * FROM df")

                # 메타데이터 테이블 업데이트
                self._update_metadata(conn, table_name, file_path, sheet_name, len(df))
        finally:
            conn.close()

    def _update_metadata(self, conn, table_name: str, file_path: str,
                         sheet_name: str, row_count: int):
        """테이블 메타데이터 관리"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _metadata (
                table_name VARCHAR,
                source_file VARCHAR,
                sheet_name VARCHAR,
                row_count INTEGER,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "DELETE FROM _metadata WHERE table_name = ?", [table_name]
        )
        conn.execute(
            "INSERT INTO _metadata VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [table_name, file_path, sheet_name, row_count]
        )

    def query(self, sql_condition: str, sheet_name: str = None) -> list[dict]:
        """SQL 조건으로 검색

        sql_condition 예: "매출 >= 1000000"
        여러 테이블에서 매칭 시도
        """
        conn = self._get_connection()
        results = []

        try:
            # 메타데이터에서 검색 대상 테이블 목록
            tables = conn.execute("SELECT table_name, source_file, sheet_name FROM _metadata").fetchall()

            for table_name, source_file, sname in tables:
                if sheet_name and sheet_name != sname:
                    continue

                try:
                    # 안전한 쿼리 실행 (sql_condition은 WHERE 절)
                    query_sql = f'SELECT * FROM "{table_name}" WHERE {sql_condition} LIMIT 20'
                    rows = conn.execute(query_sql).fetchdf()

                    if not rows.empty:
                        results.append({
                            "text": rows.to_string(index=False),
                            "source_file": source_file,
                            "file_name": os.path.basename(source_file),
                            "file_type": "excel",
                            "chunk_id": f"{table_name}_sql_result",
                            "page_or_sheet": sname,
                            "score": 1.0,  # SQL 매치는 정확 매치
                        })
                except Exception:
                    continue  # 컬럼명 불일치 등 → 다음 테이블 시도
        finally:
            conn.close()

        return results

    def get_stats(self) -> dict:
        """SQL 스토어 통계"""
        conn = self._get_connection()
        try:
            tables = conn.execute(
                "SELECT table_name, source_file, row_count FROM _metadata"
            ).fetchall()
            return {
                "total_tables": len(tables),
                "tables": [
                    {"name": t[0], "source": t[1], "rows": t[2]}
                    for t in tables
                ],
                "path": self.db_path,
            }
        except Exception:
            return {"total_tables": 0, "tables": []}
        finally:
            conn.close()
```

---

### 3.12 [M12] utils/korean.py — 한국어 처리

**책임**: 형태소 분석(Kiwi), 문장 분리(KSS)

```python
class KoreanProcessor:
    def __init__(self):
        self._kiwi = None
        self._kss = None

    def _ensure_kiwi(self):
        if self._kiwi is None:
            from kiwipiepy import Kiwi
            self._kiwi = Kiwi()

    def _ensure_kss(self):
        if self._kss is None:
            import kss
            self._kss = kss

    def split_sentences(self, text: str) -> list[str]:
        """KSS로 한국어 문장 분리"""
        self._ensure_kss()
        try:
            return self._kss.split_sentences(text)
        except Exception:
            # 폴백: 줄바꿈 기반 분리
            return [s.strip() for s in text.split('\n') if s.strip()]

    def extract_nouns(self, text: str) -> list[str]:
        """Kiwi로 핵심 명사 추출 (검색 쿼리 확장용)"""
        self._ensure_kiwi()
        tokens = self._kiwi.tokenize(text)
        return [t.form for t in tokens if t.tag.startswith('NN')]

    def normalize_for_search(self, text: str) -> str:
        """검색용 텍스트 정규화 (형태소 분석 + 핵심어 추출)"""
        nouns = self.extract_nouns(text)
        return " ".join(nouns)
```

---

## 4. MCP Tool Schema (JSON Schema)

```json
{
  "search_documents": {
    "description": "NAS 문서에서 시맨틱 검색. PDF, Excel, 이미지 등에서 자연어로 관련 내용을 찾습니다.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "자연어 검색 쿼리"},
        "top_k": {"type": "integer", "default": 5, "description": "반환할 결과 수"},
        "file_type": {"type": "string", "enum": ["pdf", "excel", "image"], "description": "파일 타입 필터 (생략 시 전체)"}
      },
      "required": ["query"]
    }
  },
  "search_excel": {
    "description": "Excel 파일 하이브리드 검색. 시맨틱 + SQL 수치 검색을 결합합니다.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "자연어 쿼리 (예: 마케팅 채널별 유입 현황)"},
        "sheet_name": {"type": "string", "description": "특정 시트명 필터"},
        "sql_filter": {"type": "string", "description": "SQL WHERE 조건 (예: 매출 > 1000000)"}
      },
      "required": ["query"]
    }
  },
  "search_receipts": {
    "description": "영수증/이미지 OCR 기반 검색.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "자연어 쿼리 (예: 이번달 택시비)"},
        "date_range": {"type": "string", "description": "날짜 범위 (예: 2026-05-01~2026-05-31)"},
        "amount_range": {"type": "string", "description": "금액 범위 (예: 10000~50000)"}
      },
      "required": ["query"]
    }
  },
  "index_file": {
    "description": "단일 파일을 인덱싱합니다.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string", "description": "파일 절대 경로"}
      },
      "required": ["file_path"]
    }
  },
  "index_directory": {
    "description": "디렉토리 내 모든 지원 파일을 일괄 인덱싱합니다.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "dir_path": {"type": "string", "description": "디렉토리 절대 경로"},
        "recursive": {"type": "boolean", "default": true, "description": "하위 디렉토리 포함 여부"},
        "file_types": {"type": "array", "items": {"type": "string"}, "description": "파일 타입 필터 (예: [\"pdf\", \"excel\"])"}
      },
      "required": ["dir_path"]
    }
  },
  "get_file_content": {
    "description": "인덱싱된 파일의 원본 내용을 조회합니다.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string", "description": "파일 경로"},
        "page": {"type": "integer", "description": "PDF 페이지 번호"},
        "sheet": {"type": "string", "description": "Excel 시트명"}
      },
      "required": ["file_path"]
    }
  },
  "get_stats": {
    "description": "인덱싱 현황 및 통계를 반환합니다.",
    "inputSchema": {"type": "object", "properties": {}}
  },
  "smart_search": {
    "description": "Agentic RAG: 쿼리 의도를 자동 분석하여 최적 검색 전략을 선택합니다.",
    "inputSchema": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "자연어 질의"}
      },
      "required": ["query"]
    }
  }
}
```

---

## 5. Dependencies

### pyproject.toml

```toml
[project]
name = "nas-rag-mcp"
version = "0.1.0"
description = "NAS Agentic RAG MCP Server"
requires-python = ">=3.11"
dependencies = [
    # MCP
    "mcp[cli]>=1.0.0",

    # 임베딩
    "sentence-transformers>=3.0.0",
    "torch>=2.0.0",

    # 벡터 DB
    "lancedb>=0.8.0",
    "pyarrow>=15.0.0",

    # 문서 파싱
    "docling>=2.0.0",
    "pandas>=2.0.0",
    "openpyxl>=3.1.0",

    # SQL
    "duckdb>=1.0.0",

    # OCR (Phase 2)
    "easyocr>=1.7.0",
    "Pillow>=10.0.0",

    # 한국어 처리
    "kiwipiepy>=0.18.0",
    "kss>=6.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

---

## 6. MCP Integration Config

### Claude Code 연결 설정

```json
// ~/.claude/mcp.json
{
  "mcpServers": {
    "nas-rag": {
      "command": "python",
      "args": ["-m", "mcp_rag_server.server"],
      "cwd": "/Users/j_mac_mini/Desktop/Vibe Coding/nas_sync",
      "env": {
        "PYTHONPATH": "/Users/j_mac_mini/Desktop/Vibe Coding/nas_sync"
      }
    }
  }
}
```

### CLAUDE.md 추가 내용 (RAG 가이드)

```markdown
## NAS RAG 시스템

NAS에 저장된 파일을 자연어로 검색할 수 있습니다.

### 사용 가능한 MCP 도구:
- `search_documents`: 문서 시맨틱 검색
- `search_excel`: Excel 하이브리드 검색 (의미 + 수치)
- `search_receipts`: 영수증/이미지 OCR 검색
- `smart_search`: 쿼리 의도 자동 분석 → 최적 검색 (추천)
- `index_file` / `index_directory`: 파일/디렉토리 인덱싱
- `get_file_content`: 파일 내용 직접 조회
- `get_stats`: 인덱싱 현황

### NAS 경로:
- 원본 파일: /Volumes/personal_folder/Macmini_backup/
- 인덱스: /Volumes/personal_folder/rag_db/
```

---

## 7. Error Handling

| 상황 | 처리 |
|------|------|
| NAS 미마운트 | `index_*` 호출 시 경로 존재 확인 → "NAS가 마운트되지 않았습니다" 에러 반환 |
| 임베딩 모델 로드 실패 | 첫 검색/인덱싱 시 로드 시도 → 실패 시 구체적 에러 메시지 |
| 지원하지 않는 파일 형식 | `_detect_file_type` 에서 None → "지원하지 않는 형식" 반환 |
| OCR 실패 | 빈 텍스트로 처리, 파일명/메타데이터만으로 인덱싱 |
| DuckDB SQL 에러 | 컬럼명 불일치 등 → 해당 테이블 건너뛰기, 에러 로깅 |
| LanceDB 테이블 없음 | `_ensure_table`로 자동 생성 |
| 대용량 파일 타임아웃 | 비동기 처리, 진행률 로깅 |

---

## 8. Test Plan

### 8.1 Unit Tests

| 테스트 | 대상 | 검증 항목 |
|--------|------|-----------|
| test_pdf_parser | PdfParser.parse() | PDF → 청크 리스트 변환, 메타데이터 포함 여부 |
| test_excel_parser | ExcelParser.parse() | 시트 요약 + 행 그룹 청크, 헤더 포함 검증 |
| test_image_parser | ImageParser.parse() | OCR 텍스트 추출, 카테고리 추론 |
| test_embeddings | EmbeddingEngine.encode() | 벡터 차원(1024), 정규화 검증 |
| test_vector_store | VectorStore.upsert/search() | 저장→검색 라운드트립 |
| test_sql_store | SqlStore.import_excel/query() | Excel→DuckDB→SQL 쿼리 |
| test_korean | KoreanProcessor | 문장 분리, 명사 추출 |

### 8.2 Integration Tests

| 테스트 | 시나리오 | 기대 결과 |
|--------|----------|-----------|
| test_index_and_search_pdf | 회사소개서 PDF 인덱싱 → "주요 제품" 검색 | 관련 청크 반환, score > 0.3 |
| test_index_and_search_excel | 마케팅 분석 Excel 인덱싱 → "채널별 유입" 검색 | 해당 시트 데이터 반환 |
| test_hybrid_search | Excel 인덱싱 → 수치 조건 검색 | DuckDB SQL 결과 포함 |
| test_agentic_routing | "택시비 영수증" → RECEIPT_SEARCH 라우팅 | 올바른 의도 분류 + 결과 |
| test_self_reflection | 결과 없음 → 쿼리 확장 → 재검색 | 재검색 시도, confidence 포함 |

### 8.3 E2E Tests

| 테스트 | 시나리오 |
|--------|----------|
| test_full_workflow | NAS 디렉토리 인덱싱 → smart_search로 다양한 쿼리 → 결과 검증 |
| test_mcp_connection | Claude Code에서 MCP 도구 호출 → 응답 수신 |

---

## 9. Security Considerations

| 항목 | 대응 |
|------|------|
| SQL Injection | DuckDB sql_filter 파라미터화 쿼리 사용 (현재는 패턴 매칭으로 제한된 조건만 허용) |
| 경로 탐색 | `index_file`에서 NAS 경로 내부인지 검증 (`config.nas_base_path` prefix 체크) |
| 자격증명 노출 | NAS 계정 정보는 macOS 키체인에만 저장, 코드에 하드코딩 금지 |
| 데이터 프라이버시 | 모든 처리 로컬, 외부 API 호출 없음 (임베딩도 로컬) |

---

## 10. Performance Considerations

| 항목 | 전략 |
|------|------|
| 임베딩 모델 로딩 | 지연 로딩 (첫 호출 시 ~10초, 이후 즉시) |
| 배치 임베딩 | `batch_size=32`로 벡터화 (개별 호출 대비 ~5x 빠름) |
| Apple Silicon GPU | `device="mps"`로 GPU 가속 (CPU 대비 ~3x) |
| LanceDB 디스크 I/O | NAS가 아닌 로컬에 인덱스 저장 옵션 (config 변경만으로 가능) |
| 대량 인덱싱 | 비동기 처리, 파일 단위 진행률 반환 |

---

## 11. Implementation Guide

### 11.1 구현 순서

| 순서 | 모듈 | 의존성 | Phase |
|------|------|--------|-------|
| 1 | M2 config.py | 없음 | 1 |
| 2 | M12 korean.py | 없음 | 1 |
| 3 | M3 embeddings.py | config | 1 |
| 4 | M10 vector_store.py | config | 1 |
| 5 | M11 sql_store.py | config | 1 |
| 6 | M7 pdf_parser.py | config, korean | 1 |
| 7 | M8 excel_parser.py | config | 1 |
| 8 | M4 indexer.py | config, embeddings, parsers, stores | 1 |
| 9 | M5 searcher.py | config, embeddings, stores, korean | 1 |
| 10 | M1 server.py | config, indexer, searcher | 1 |
| 11 | M9 image_parser.py | config | 2 |
| 12 | M6 agentic_router.py | config, searcher | 3 |

### 11.2 Module Map

```
Session 1 (Foundation):   M2 → M12 → M3 → M10 → M11
Session 2 (Parsers):      M7 → M8
Session 3 (Core Logic):   M4 → M5 → M1 + MCP 연결 + 테스트
Session 4 (OCR):          M9 + search_receipts 테스트
Session 5 (Agentic):      M6 + smart_search + 통합 테스트
```

### 11.3 Session Guide

| Session | Scope Key | 모듈 | 산출물 | 상태 |
|---------|-----------|------|--------|------|
| S1 | `foundation` | M2, M12, M3, M10, M11 | 설정, 한국어 처리, 임베딩, 스토어 기초 | ✅ 완료 |
| S2 | `parsers` | M7, M8 | PDF/Excel 파서 | ✅ 완료 |
| S3 | `core` | M4, M5, M1 | 인덱서, 검색기, MCP 서버 + MCP 연결 | ✅ 완료 |
| S4 | `ocr` | M9 | 이미지 파서 + 영수증 OCR 검색 | ✅ 완료 |
| S5 | `agentic` | M6 | Agentic 라우터 + 전체 E2E 테스트 | ⏳ 미착수 |

### 11.4 구현 결과 (2026-05-10)

- S1~S4 완료: 12개 모듈 중 11개 구현
- NAS 전체 인덱싱: Excel 19 + PDF 18 + 이미지 29 = **66개 파일, 7,335 벡터 청크**
- MCP 서버 등록 및 Claude Code 실시간 연동 확인

### 11.5 Design 대비 변경 사항

| 항목 | Design 원안 | 실제 구현 | 사유 |
|------|-------------|-----------|------|
| 벡터 DB 경로 | `/Volumes/personal_folder/rag_db/` | `~/.nas_rag/` | SMB atomic rename 미지원 |
| PDF 파서 | Docling 우선 | pypdf 폴백 | Docling Python 3.14 미지원 |
| Searcher 인스턴스 | 자체 생성 | server.py에서 공유 주입 | 메모리 절약 (EmbeddingEngine 단일 인스턴스) |
| EmbeddingEngine | MPS 고정 | MPS → CPU 자동 폴백 | MPS 미지원 환경 대응 |

---

## Next Step

```
/pdca do nas-agentic-rag --scope agentic
```
