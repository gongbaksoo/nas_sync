# Design Ref: §3.2 — 모든 경로, 모델명, 파라미터를 중앙 관리
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # NAS 경로
    nas_base_path: Path = Path("/Volumes/personal_folder")
    nas_backup_path: Path = Path("/Volumes/personal_folder/Macmini_backup")

    # 인덱스 저장 경로 (로컬 — SMB/NAS는 atomic rename 미지원으로 LanceDB 사용 불가)
    vector_db_path: Path = Path.home() / ".nas_rag" / "lancedb"
    sql_db_path: Path = Path.home() / ".nas_rag" / "excel_data.duckdb"

    # 임베딩 모델
    embedding_model: str = "upskyy/bge-m3-korean"
    embedding_dimension: int = 1024

    # 청킹 파라미터
    pdf_chunk_size: int = 800
    pdf_chunk_overlap: int = 80
    excel_row_group_size: int = 15

    # 검색 파라미터
    default_top_k: int = 5
    similarity_threshold: float = 0.3

    # 지원 확장자
    supported_extensions: dict = field(default_factory=lambda: {
        "pdf": [".pdf"],
        "excel": [".xlsx", ".xls"],
        "image": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    })

    def is_nas_mounted(self) -> bool:
        return self.nas_base_path.exists()

    def ensure_dirs(self):
        self.vector_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sql_db_path.parent.mkdir(parents=True, exist_ok=True)
