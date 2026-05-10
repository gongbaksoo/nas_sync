# Design Ref: §3.7 — Docling PDF 파싱, KSS 한국어 시맨틱 청킹
import logging
import os
from datetime import datetime

from mcp_rag_server.config import Config
from mcp_rag_server.utils.korean import KoreanProcessor

logger = logging.getLogger(__name__)


class PdfParser:
    def __init__(self, config: Config):
        self.config = config
        self.korean = KoreanProcessor()
        self._converter = None

    def _ensure_converter(self):
        """지연 로딩: Docling은 무거우므로 필요할 때만 로드"""
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()

    def parse(self, file_path: str) -> list[dict]:
        """PDF -> 청크 리스트

        1. Docling으로 텍스트 + 테이블 추출 (Markdown 형식)
        2. KSS로 한국어 문장 분리
        3. 시맨틱 청킹 (config.pdf_chunk_size 기준)
        4. 메타데이터 첨부
        """
        try:
            self._ensure_converter()
            result = self._converter.convert(file_path)
            full_text = result.document.export_to_markdown()
        except Exception as e:
            logger.warning("Docling 파싱 실패, pypdf 폴백 시도: %s", e)
            full_text = self._fallback_parse(file_path)

        if not full_text or not full_text.strip():
            logger.warning("빈 텍스트: %s", file_path)
            return []

        sentences = self.korean.split_sentences(full_text)
        chunks = self._create_chunks(sentences, file_path)

        logger.info("%s: %d 청크 생성", os.path.basename(file_path), len(chunks))
        return chunks

    def _fallback_parse(self, file_path: str) -> str:
        """Docling 실패 시 pypdf로 폴백"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
        except Exception as e:
            logger.error("pypdf 폴백도 실패: %s", e)
            return ""

    def _create_chunks(self, sentences: list[str], file_path: str) -> list[dict]:
        """문장 리스트 -> 청크 리스트 (크기 기반 그룹화 + 오버랩)"""
        chunks = []
        current_text = ""
        chunk_idx = 0
        file_name = os.path.basename(file_path)
        chunk_size = self.config.pdf_chunk_size
        overlap = self.config.pdf_chunk_overlap

        for sentence in sentences:
            if len(current_text) + len(sentence) > chunk_size and current_text.strip():
                chunks.append(self._make_chunk(
                    text=current_text.strip(),
                    file_path=file_path,
                    file_name=file_name,
                    chunk_idx=chunk_idx,
                ))
                chunk_idx += 1
                # 오버랩: 마지막 일부 텍스트 유지
                current_text = current_text[-overlap:] + sentence + " "
            else:
                current_text += sentence + " "

        # 마지막 청크
        if current_text.strip():
            chunks.append(self._make_chunk(
                text=current_text.strip(),
                file_path=file_path,
                file_name=file_name,
                chunk_idx=chunk_idx,
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
            "date_created": datetime.fromtimestamp(
                os.path.getmtime(file_path)
            ).isoformat(),
            "date_indexed": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(file_path),
            "language": "ko",
        }
