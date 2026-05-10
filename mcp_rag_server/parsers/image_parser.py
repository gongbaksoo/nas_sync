# Design Ref: §3.9 — EasyOCR 이미지/영수증 파싱, 메타데이터 추론
import logging
import os
from datetime import datetime

from mcp_rag_server.config import Config

logger = logging.getLogger(__name__)


class ImageParser:
    def __init__(self, config: Config):
        self.config = config
        self._reader = None

    def _ensure_reader(self):
        """지연 로딩: EasyOCR는 무거우므로 필요할 때만 로드"""
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(["ko", "en"], gpu=True)
            logger.info("EasyOCR 리더 로드 완료 (ko, en)")

    def parse(self, file_path: str) -> list[dict]:
        """이미지 -> 청크 (OCR 텍스트 + 메타데이터)

        1개 이미지 = 1개 청크
        """
        self._ensure_reader()
        file_name = os.path.basename(file_path)

        # OCR 실행
        ocr_text = ""
        ocr_confidence = 0.0
        try:
            ocr_results = self._reader.readtext(file_path, detail=1)
            if ocr_results:
                ocr_text = " ".join(r[1] for r in ocr_results)
                ocr_confidence = sum(r[2] for r in ocr_results) / len(ocr_results)
        except Exception as e:
            logger.warning("OCR 실패 (%s): %s", file_name, e)

        # 이미지 해상도
        resolution = "unknown"
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                resolution = f"{img.width}x{img.height}"
        except Exception:
            pass

        # 폴더 경로에서 카테고리 추론
        category = self._infer_category(file_path)

        # 텍스트 구성
        text_parts = [f"파일: {file_name}"]
        if category:
            text_parts.append(f"분류: {category}")
        if ocr_text:
            text_parts.append(f"내용: {ocr_text}")
        else:
            text_parts.append("내용: (텍스트 추출 없음)")

        chunk = {
            "text": "\n".join(text_parts),
            "source_file": file_path,
            "file_name": file_name,
            "file_type": "image",
            "chunk_id": f"{file_name}_ocr",
            "page_or_sheet": "",
            "date_created": datetime.fromtimestamp(
                os.path.getmtime(file_path)
            ).isoformat(),
            "date_indexed": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(file_path),
            "language": "ko",
            "ocr_text": ocr_text,
            "ocr_confidence": round(ocr_confidence, 2),
            "resolution": resolution,
            "category": category,
        }

        status = f"OCR {len(ocr_text)}자" if ocr_text else "OCR 없음"
        logger.info("%s: %s, %s", file_name, status, resolution)

        return [chunk]

    def _infer_category(self, file_path: str) -> str:
        """폴더 경로에서 카테고리 추론

        예: /개인경비/2403/240313_택시비.jpg -> "개인경비/2403"
        """
        parts = file_path.split(os.sep)
        category_keywords = [
            "경비", "상품", "이미지", "영수증", "사진",
            "택시", "식대", "접대", "교통", "오염",
        ]
        for i, part in enumerate(parts):
            if any(kw in part for kw in category_keywords):
                remaining = parts[i:len(parts) - 1]  # 파일명 제외
                return "/".join(remaining) if remaining else part
        return ""
