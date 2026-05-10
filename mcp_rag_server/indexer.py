# Design Ref: §3.4 — 파일 탐지 -> 파서 선택 -> 청킹 -> 임베딩 -> 스토어 저장
import logging
import os
from datetime import datetime
from pathlib import Path

from mcp_rag_server.config import Config
from mcp_rag_server.embeddings import EmbeddingEngine
from mcp_rag_server.parsers.pdf_parser import PdfParser
from mcp_rag_server.parsers.excel_parser import ExcelParser
from mcp_rag_server.parsers.image_parser import ImageParser
from mcp_rag_server.stores.vector_store import VectorStore
from mcp_rag_server.stores.sql_store import SqlStore

logger = logging.getLogger(__name__)


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

    def _validate_path(self, file_path: str) -> str | None:
        """경로 유효성 검증. 에러 메시지 반환, 정상이면 None"""
        if not self.config.is_nas_mounted():
            return "NAS가 마운트되지 않았습니다. Finder에서 smb://192.168.0.235/personal_folder 에 연결해주세요."
        if not os.path.exists(file_path):
            return f"파일을 찾을 수 없음: {file_path}"
        return None

    async def index_file(self, file_path: str) -> dict:
        """단일 파일 인덱싱

        Plan SC: 자연어로 NAS 파일 검색 가능 (인덱싱이 전제)
        """
        # 경로 검증
        error = self._validate_path(file_path)
        if error:
            return {"status": "error", "message": error}

        file_type = self._detect_file_type(file_path)
        if not file_type:
            return {"status": "error", "message": f"지원하지 않는 파일 형식: {Path(file_path).suffix}"}

        if file_type not in self.parsers:
            return {"status": "error", "message": f"'{file_type}' 파서가 아직 구현되지 않았습니다 (Phase 2에서 추가 예정)"}

        # 1. 파싱 -> 청크 리스트
        parser = self.parsers[file_type]
        try:
            chunks = parser.parse(file_path)
        except Exception as e:
            logger.error("파싱 실패: %s — %s", file_path, e)
            return {"status": "error", "message": f"파싱 실패: {e}"}

        if not chunks:
            return {"status": "error", "message": "파싱 결과가 비어있음 (파일이 비어있거나 지원하지 않는 형식)"}

        # 2. 임베딩
        texts = [c["text"] for c in chunks]
        try:
            vectors = self.embeddings.encode(texts)
        except Exception as e:
            logger.error("임베딩 실패: %s", e)
            return {"status": "error", "message": f"임베딩 실패: {e}"}

        # 3. 벡터 스토어 저장
        self.vector_store.upsert(chunks, vectors)

        # 4. Excel인 경우 SQL 스토어에도 저장
        if file_type == "excel":
            try:
                self.sql_store.import_excel(file_path)
            except Exception as e:
                logger.warning("SQL 스토어 임포트 실패 (벡터 인덱싱은 성공): %s", e)

        return {
            "status": "success",
            "file": file_path,
            "file_name": os.path.basename(file_path),
            "type": file_type,
            "chunks": len(chunks),
            "indexed_at": datetime.now().isoformat(),
        }

    async def index_directory(self, dir_path: str, recursive: bool = True,
                              file_types: list[str] | None = None) -> dict:
        """디렉토리 내 모든 지원 파일 일괄 인덱싱"""
        error = self._validate_path(dir_path)
        if error:
            return {"status": "error", "message": error}

        if not os.path.isdir(dir_path):
            return {"status": "error", "message": f"디렉토리가 아님: {dir_path}"}

        results = {"total": 0, "success": 0, "failed": 0, "skipped": 0, "files": []}

        for root, _, files in os.walk(dir_path):
            if not recursive and root != dir_path:
                continue
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                ftype = self._detect_file_type(fpath)

                if ftype is None:
                    continue
                if file_types and ftype not in file_types:
                    results["skipped"] += 1
                    continue
                if ftype not in self.parsers:
                    results["skipped"] += 1
                    continue

                logger.info("인덱싱 중: %s", fpath)
                result = await self.index_file(fpath)
                results["total"] += 1

                if result["status"] == "success":
                    results["success"] += 1
                else:
                    results["failed"] += 1

                results["files"].append(result)

        logger.info(
            "디렉토리 인덱싱 완료: %d 성공, %d 실패, %d 건너뜀",
            results["success"], results["failed"], results["skipped"],
        )
        return results

    async def get_stats(self) -> dict:
        """인덱싱 현황 통계"""
        vector_stats = self.vector_store.get_stats()
        sql_stats = self.sql_store.get_stats()
        return {
            "vector_store": vector_stats,
            "sql_store": sql_stats,
            "supported_parsers": list(self.parsers.keys()),
            "config": {
                "embedding_model": self.config.embedding_model,
                "nas_path": str(self.config.nas_backup_path),
                "nas_mounted": self.config.is_nas_mounted(),
            },
        }
