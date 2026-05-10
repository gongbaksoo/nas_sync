# Design Ref: §3.1 — MCP 서버 엔트리포인트, 도구 등록, 요청 라우팅
# Design Ref: §4 — MCP Tool Schema (JSON Schema)
import asyncio
import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from mcp_rag_server.config import Config
from mcp_rag_server.embeddings import EmbeddingEngine
from mcp_rag_server.indexer import Indexer
from mcp_rag_server.searcher import Searcher
from mcp_rag_server.stores.vector_store import VectorStore
from mcp_rag_server.stores.sql_store import SqlStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("nas-rag")

app = Server("nas-rag")

# 지연 초기화: 도구 호출 시점에 생성
_config: Config | None = None
_indexer: Indexer | None = None
_searcher: Searcher | None = None


def _ensure_initialized():
    """컴포넌트 지연 초기화 — 첫 도구 호출 시 한 번만 실행"""
    global _config, _indexer, _searcher
    if _config is not None:
        return

    _config = Config()
    _config.ensure_dirs()

    embeddings = EmbeddingEngine(_config)
    vector_store = VectorStore(_config)
    sql_store = SqlStore(_config)

    _indexer = Indexer(_config)
    # Searcher와 Indexer가 같은 인스턴스를 공유하도록 연결
    _indexer.embeddings = embeddings
    _indexer.vector_store = vector_store
    _indexer.sql_store = sql_store

    _searcher = Searcher(_config, embeddings, vector_store, sql_store)

    logger.info("NAS RAG MCP 서버 초기화 완료")


# --- Tool Definitions ---

TOOLS = [
    Tool(
        name="search_documents",
        description="NAS 문서에서 시맨틱 검색. PDF, Excel 등에서 자연어로 관련 내용을 찾습니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "자연어 검색 쿼리"},
                "top_k": {"type": "integer", "default": 5, "description": "반환할 결과 수"},
                "file_type": {
                    "type": "string",
                    "enum": ["pdf", "excel", "image"],
                    "description": "파일 타입 필터 (생략 시 전체)",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="search_excel",
        description="Excel 파일 하이브리드 검색. 시맨틱 + SQL 수치 검색을 결합합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "자연어 쿼리 (예: 마케팅 채널별 유입 현황)"},
                "sheet_name": {"type": "string", "description": "특정 시트명 필터"},
                "sql_filter": {"type": "string", "description": "SQL WHERE 조건 (예: 매출 > 1000000)"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="search_receipts",
        description="영수증/이미지 OCR 기반 검색.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "자연어 쿼리 (예: 이번달 택시비)"},
                "date_range": {"type": "string", "description": "날짜 범위 (예: 2026-05-01~2026-05-31)"},
                "amount_range": {"type": "string", "description": "금액 범위 (예: 10000~50000)"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="index_file",
        description="단일 파일을 인덱싱합니다. PDF, Excel 파일을 벡터 DB에 저장하여 검색 가능하게 만듭니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "파일 절대 경로"},
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="index_directory",
        description="디렉토리 내 모든 지원 파일을 일괄 인덱싱합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "dir_path": {"type": "string", "description": "디렉토리 절대 경로"},
                "recursive": {"type": "boolean", "default": True, "description": "하위 디렉토리 포함 여부"},
                "file_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "파일 타입 필터 (예: [\"pdf\", \"excel\"])",
                },
            },
            "required": ["dir_path"],
        },
    ),
    Tool(
        name="get_file_content",
        description="인덱싱된 파일의 원본 내용을 조회합니다.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "파일 경로"},
                "page": {"type": "integer", "description": "PDF 페이지 번호"},
                "sheet": {"type": "string", "description": "Excel 시트명"},
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="get_stats",
        description="인덱싱 현황 및 통계를 반환합니다.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    _ensure_initialized()

    try:
        result = await _dispatch(name, arguments)
    except Exception as e:
        logger.error("도구 실행 에러 [%s]: %s", name, e, exc_info=True)
        result = {"status": "error", "message": str(e)}

    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return [TextContent(type="text", text=text)]


async def _dispatch(name: str, arguments: dict) -> dict | list:
    """도구명 -> 핸들러 라우팅"""
    match name:
        case "search_documents":
            return await _searcher.search_documents(**arguments)
        case "search_excel":
            return await _searcher.search_excel(**arguments)
        case "search_receipts":
            return await _searcher.search_receipts(**arguments)
        case "index_file":
            return await _indexer.index_file(**arguments)
        case "index_directory":
            return await _indexer.index_directory(**arguments)
        case "get_file_content":
            return await _searcher.get_file_content(**arguments)
        case "get_stats":
            return await _indexer.get_stats()
        case _:
            return {"status": "error", "message": f"알 수 없는 도구: {name}"}


async def main():
    logger.info("NAS RAG MCP 서버 시작")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
