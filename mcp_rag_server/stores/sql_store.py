# Design Ref: §3.11 — DuckDB 래퍼, Excel 수치 검색용
import logging
import os
import re

import duckdb
import pandas as pd

from mcp_rag_server.config import Config

logger = logging.getLogger(__name__)


class SqlStore:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = str(config.sql_db_path)
        config.ensure_dirs()

    def _get_connection(self):
        return duckdb.connect(self.db_path)

    def _sanitize_table_name(self, name: str) -> str:
        """테이블명으로 사용 가능한 형태로 변환"""
        safe = re.sub(r"[^\w]", "_", name)
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe[:60]

    def import_excel(self, file_path: str):
        """Excel 파일의 모든 시트를 DuckDB 테이블로 임포트"""
        conn = self._get_connection()
        file_name = os.path.basename(file_path)

        try:
            xls = pd.ExcelFile(file_path)
            imported = 0
            for sheet_name in xls.sheet_names:
                try:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                except Exception:
                    continue

                if df.empty:
                    continue

                table_name = self._sanitize_table_name(f"{file_name}_{sheet_name}")
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                conn.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM df')
                self._update_metadata(conn, table_name, file_path, sheet_name, len(df))
                imported += 1

            logger.info("%s: %d 시트 임포트 완료", file_name, imported)
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
        conn.execute("DELETE FROM _metadata WHERE table_name = ?", [table_name])
        conn.execute(
            "INSERT INTO _metadata VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [table_name, file_path, sheet_name, row_count],
        )

    def query(self, sql_condition: str, sheet_name: str | None = None) -> list[dict]:
        """SQL 조건으로 검색. 여러 테이블에서 매칭 시도."""
        conn = self._get_connection()
        results = []

        try:
            try:
                tables = conn.execute(
                    "SELECT table_name, source_file, sheet_name FROM _metadata"
                ).fetchall()
            except duckdb.CatalogException:
                return []

            for table_name, source_file, sname in tables:
                if sheet_name and sheet_name != sname:
                    continue

                try:
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
                            "score": 1.0,
                        })
                except Exception:
                    continue
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
