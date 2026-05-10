# Design Ref: §3.8 — pandas Excel 파싱, 시트 요약 + 행 그룹 청킹
import logging
import os
from datetime import datetime

import pandas as pd

from mcp_rag_server.config import Config

logger = logging.getLogger(__name__)


class ExcelParser:
    def __init__(self, config: Config):
        self.config = config

    def parse(self, file_path: str) -> list[dict]:
        """Excel -> 청크 리스트

        시트마다:
        1. 시트 요약 청크 (컬럼명, 행 수, 수치 통계)
        2. 행 그룹 청크 (헤더 항상 포함, 15행 단위)
        """
        chunks = []
        file_name = os.path.basename(file_path)

        try:
            xls = pd.ExcelFile(file_path)
        except Exception as e:
            logger.error("Excel 파일 열기 실패: %s — %s", file_path, e)
            return []

        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            except Exception as e:
                logger.warning("시트 '%s' 읽기 실패: %s", sheet_name, e)
                continue

            if df.empty:
                continue

            # 1. 시트 요약 청크
            summary = self._create_summary(df, file_path, file_name, sheet_name)
            chunks.append(summary)

            # 2. 행 그룹 청크
            row_chunks = self._create_row_groups(df, file_path, file_name, sheet_name)
            chunks.extend(row_chunks)

        logger.info("%s: %d 시트, %d 청크 생성", file_name, len(xls.sheet_names), len(chunks))
        return chunks

    def _create_summary(self, df: pd.DataFrame, file_path: str,
                        file_name: str, sheet_name: str) -> dict:
        """시트 요약 청크 생성 — 컬럼, 행 수, 수치 통계 포함"""
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
            try:
                summary_lines.append(
                    f"{col}: 합계={df[col].sum():,.0f}, "
                    f"평균={df[col].mean():,.1f}, "
                    f"최소={df[col].min():,.0f}, "
                    f"최대={df[col].max():,.0f}"
                )
            except Exception:
                continue

        return {
            "text": "\n".join(summary_lines),
            "source_file": file_path,
            "file_name": file_name,
            "file_type": "excel",
            "chunk_id": f"{file_name}_{sheet_name}_summary",
            "page_or_sheet": sheet_name,
            "columns": [str(c) for c in columns],
            "date_created": datetime.fromtimestamp(
                os.path.getmtime(file_path)
            ).isoformat(),
            "date_indexed": datetime.now().isoformat(),
            "size_bytes": os.path.getsize(file_path),
            "language": "ko",
            "row_range": "summary",
        }

    def _create_row_groups(self, df: pd.DataFrame, file_path: str,
                           file_name: str, sheet_name: str) -> list[dict]:
        """행 그룹 청크 생성 — 헤더 항상 포함, group_size행 단위"""
        chunks = []
        header = " | ".join(str(c) for c in df.columns)
        group_size = self.config.excel_row_group_size

        for i in range(0, len(df), group_size):
            group = df.iloc[i:i + group_size]
            text_lines = [
                f"파일: {file_name} / 시트: {sheet_name}",
                f"헤더: {header}",
                f"행 {i + 1}-{i + len(group)}:",
                group.to_string(index=False),
            ]

            chunks.append({
                "text": "\n".join(text_lines),
                "source_file": file_path,
                "file_name": file_name,
                "file_type": "excel",
                "chunk_id": f"{file_name}_{sheet_name}_rows_{i}-{i + len(group)}",
                "page_or_sheet": sheet_name,
                "columns": [str(c) for c in df.columns],
                "date_created": datetime.fromtimestamp(
                    os.path.getmtime(file_path)
                ).isoformat(),
                "date_indexed": datetime.now().isoformat(),
                "size_bytes": os.path.getsize(file_path),
                "language": "ko",
                "row_range": f"{i}-{i + len(group)}",
            })

        return chunks
