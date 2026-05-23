"""Spreadsheet loading helpers for real Excel files and HTML-exported .xls."""
from __future__ import annotations

import os
from collections.abc import Iterable

import pandas as pd


CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"


def read_spreadsheet_sheets(file_path: str) -> list[tuple[str, pd.DataFrame]]:
    """Return spreadsheet-like sheets as `(sheet_name, dataframe)` tuples.

    Several commerce exports use `.xls` extensions for HTML tables. Pandas cannot
    infer those reliably from the extension, so sniff the file header first.
    """
    kind = _detect_kind(file_path)

    if kind == "html":
        return _read_html_tables(file_path)

    if kind == "xls":
        return _read_excel_sheets(file_path, engine="xlrd")

    if kind == "xlsx":
        return _read_excel_sheets(file_path, engine="openpyxl")

    return _read_unknown(file_path)


def _detect_kind(file_path: str) -> str:
    with open(file_path, "rb") as f:
        header = f.read(4096)

    stripped = header.lstrip()
    lowered = stripped[:512].lower()

    if stripped.startswith(CFB_MAGIC):
        return "xls"
    if stripped.startswith(ZIP_MAGIC):
        return "xlsx"
    if b"<html" in lowered or b"<table" in lowered or b"<!doctype html" in lowered:
        return "html"
    if b"<meta" in lowered and b"text/html" in lowered:
        return "html"

    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".xlsx", ".xlsm"}:
        return "xlsx"
    if ext == ".xls":
        return "unknown"
    return "unknown"


def _read_excel_sheets(file_path: str, engine: str | None = None) -> list[tuple[str, pd.DataFrame]]:
    xls = pd.ExcelFile(file_path, engine=engine)
    sheets = []

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name, engine=engine)
        df = _normalize_dataframe(df)
        if not df.empty:
            sheets.append((str(sheet_name), df))

    return sheets


def _read_html_tables(file_path: str) -> list[tuple[str, pd.DataFrame]]:
    tables = pd.read_html(file_path)
    sheets = []

    for idx, df in enumerate(tables, start=1):
        df = _normalize_dataframe(df)
        if not df.empty:
            sheets.append((f"Table {idx}", df))

    return sheets


def _read_unknown(file_path: str) -> list[tuple[str, pd.DataFrame]]:
    attempts = (
        lambda: _read_excel_sheets(file_path),
        lambda: _read_html_tables(file_path),
        lambda: [("CSV", _normalize_dataframe(pd.read_csv(file_path, sep=None, engine="python")))],
    )

    last_error: Exception | None = None
    for attempt in attempts:
        try:
            sheets = attempt()
            if sheets:
                return sheets
        except Exception as e:
            last_error = e

    if last_error:
        raise last_error
    return []


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty:
        return df

    df = df.copy()
    df.columns = _unique_column_names(_flatten_columns(df.columns))
    return df


def _flatten_columns(columns: Iterable[object]) -> list[str]:
    names = []
    for col in columns:
        if isinstance(col, tuple):
            name = " ".join(str(part) for part in col if str(part) != "nan").strip()
        else:
            name = str(col).strip()
        names.append(name or "column")
    return names


def _unique_column_names(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique = []

    for col in columns:
        count = seen.get(col, 0)
        seen[col] = count + 1
        unique.append(col if count == 0 else f"{col}_{count + 1}")

    return unique
