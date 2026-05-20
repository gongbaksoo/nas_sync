"""NAS 자동 인덱싱 — 동기화 후 변경된 파일만 감지하여 인덱싱

sync_to_nas.sh 에서 호출됨. 마지막 인덱싱 시점 이후 변경된 파일만 처리.
"""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_rag_server.config import Config
from mcp_rag_server.indexer import Indexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)
logger = logging.getLogger("auto-index")

MARKER_FILE = Path.home() / ".nas_rag" / "last_indexed.json"


def load_marker() -> dict:
    """마지막 인덱싱 시점 로드"""
    if MARKER_FILE.exists():
        return json.loads(MARKER_FILE.read_text())
    return {"last_run": 0, "indexed_files": {}}


def save_marker(marker: dict):
    MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    MARKER_FILE.write_text(json.dumps(marker, ensure_ascii=False, indent=2))


def find_changed_files(config: Config, marker: dict) -> list[str]:
    """마지막 인덱싱 이후 변경/추가된 파일 탐색"""
    last_run = marker.get("last_run", 0)
    indexed_files = marker.get("indexed_files", {})
    changed = []

    nas_path = str(config.nas_backup_path)
    if not os.path.isdir(nas_path):
        logger.warning("NAS 경로 없음: %s", nas_path)
        return []

    all_extensions = set()
    for exts in config.supported_extensions.values():
        all_extensions.update(exts)

    for root, _, files in os.walk(nas_path):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in all_extensions:
                continue
            if fname.startswith("~$") or fname == ".DS_Store":
                continue

            fpath = os.path.join(root, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except OSError:
                continue

            prev_mtime = indexed_files.get(fpath, 0)
            if mtime > prev_mtime:
                changed.append(fpath)

    return changed


def init_marker():
    """기존 NAS 파일의 mtime을 마커에 기록 (첫 실행 시 전체 인덱싱 방지)

    이미 인덱싱된 파일은 건너뛰고, 이후 변경분만 처리하도록 기준점을 설정.
    """
    config = Config()
    if not config.is_nas_mounted():
        logger.error("NAS 미마운트")
        return

    all_extensions = set()
    for exts in config.supported_extensions.values():
        all_extensions.update(exts)

    indexed_files = {}
    nas_path = str(config.nas_backup_path)
    for root, _, files in os.walk(nas_path):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in all_extensions:
                continue
            if fname.startswith("~$"):
                continue
            fpath = os.path.join(root, fname)
            try:
                indexed_files[fpath] = os.path.getmtime(fpath)
            except OSError:
                continue

    marker = {"last_run": time.time(), "indexed_files": indexed_files}
    save_marker(marker)
    logger.info("마커 초기화 완료: %d개 파일 기록", len(indexed_files))


async def run_indexing():
    config = Config()

    if not config.is_nas_mounted():
        logger.error("NAS 미마운트 — 인덱싱 건너뜀")
        return

    marker = load_marker()

    # 마커가 없으면 초기화 후 종료 (첫 실행)
    if marker["last_run"] == 0:
        logger.info("첫 실행 감지 — 마커 초기화 (기존 파일 기록만, 인덱싱 없음)")
        init_marker()
        return

    changed = find_changed_files(config, marker)

    if not changed:
        logger.info("변경된 파일 없음 — 인덱싱 건너뜀")
        return

    logger.info("변경 감지: %d개 파일 인덱싱 시작", len(changed))

    indexer = Indexer(config)
    success = 0
    failed = 0

    for fpath in changed:
        try:
            result = await indexer.index_file(fpath)
            if result["status"] == "success":
                success += 1
                marker.setdefault("indexed_files", {})[fpath] = os.path.getmtime(fpath)
                marker["last_run"] = time.time()
                save_marker(marker)
                logger.info("  OK: %s (%d 청크)", result["file_name"], result["chunks"])
            else:
                failed += 1
                marker.setdefault("indexed_files", {})[fpath] = os.path.getmtime(fpath)
                marker["last_run"] = time.time()
                save_marker(marker)
                logger.warning("  FAIL: %s — %s", os.path.basename(fpath), result.get("message"))
        except Exception as e:
            failed += 1
            try:
                marker.setdefault("indexed_files", {})[fpath] = os.path.getmtime(fpath)
                marker["last_run"] = time.time()
                save_marker(marker)
            except OSError:
                pass
            logger.error("  ERROR: %s — %s", os.path.basename(fpath), e)

    marker["last_run"] = time.time()
    save_marker(marker)

    logger.info("인덱싱 완료: %d 성공, %d 실패 (총 %d)", success, failed, len(changed))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        init_marker()
    else:
        asyncio.run(run_indexing())
