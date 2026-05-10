# Development History

NAS Agentic RAG 프로젝트 개발 이력.

---

## 2026-05-09: Plan Plus + Design

### Plan Phase (Plan Plus)
- 인수인계서(`NAS_동기화_인수인계.md`) 분석
- 심층 리서치 수행 → `Agentic_RAG_구축_실전_가이드.md` 생성 (800줄+)
  - RAG 실전 경험담 (100+ 팀 베스트 프랙티스)
  - Agentic RAG 아키텍처 패턴 5가지
  - 로컬/NAS RAG 스택 비교 (LanceDB vs ChromaDB vs Qdrant)
  - MCP 통합 패턴 (기존 서버 4개 분석)
  - 비정형 데이터(Excel, 이미지, 한국어) 처리 전략
- 사용자 의사결정: 커스텀 MCP RAG 서버 + 전 기능 포함 (3단계 구현)
- Plan 문서 생성: `docs/01-plan/features/nas-agentic-rag.plan.md`

### Design Phase
- 3가지 아키텍처 옵션 제시 (Monolith / Clean Arch / Pragmatic)
- 사용자 선택: Option C — Pragmatic Balance (12개 모듈)
- Design 문서 생성: `docs/02-design/features/nas-agentic-rag.design.md`
- 기술 스택 확정: LanceDB + BGE-m3-ko + Docling + EasyOCR + DuckDB + MCP Python SDK

---

## 2026-05-10: Implementation (Session 1~4)

### Session 1: Foundation (M2, M12, M3, M10, M11)
- 프로젝트 구조 생성 (`mcp_rag_server/` 패키지)
- `config.py`: NAS 경로, 모델명, 파라미터 중앙 관리
- `korean.py`: KSS 문장 분리 + Kiwi 명사 추출 (지연 로딩)
- `embeddings.py`: BGE-m3-ko 래퍼 (MPS GPU + CPU 폴백)
- `vector_store.py`: LanceDB 래퍼 (스키마 생성, upsert, search, stats)
- `sql_store.py`: DuckDB 래퍼 (Excel 임포트, SQL 쿼리, 메타데이터)
- `pyproject.toml`: 의존성 정의

### Session 2: Parsers (M7, M8)
- `pdf_parser.py`: Docling 우선 + pypdf 폴백, KSS 시맨틱 청킹
- `excel_parser.py`: 시트 요약 + 행 그룹 청킹 (헤더 항상 포함)

### Session 3: Core (M4, M5, M1)
- `indexer.py`: 파일 탐지 → 파서 → 임베딩 → 스토어 저장
- `searcher.py`: 벡터/SQL/하이브리드 검색 + 결과 정규화
- `server.py`: MCP 서버 엔트리포인트 (7개 도구 등록)
- 의존성 설치: `pip install` (mcp, lancedb, sentence-transformers, torch, duckdb, pandas 등)

### 테스트 & 트러블슈팅
- **ERR-001**: LanceDB NAS 저장 실패 → 로컬 `~/.nas_rag/`로 변경
- **ERR-002**: Docling Python 3.14 미지원 → pypdf 폴백 적용
- **ERR-003**: PDF 폴백 미동작 → try/except 범위 수정
- Excel 인덱싱 성공 (3개 파일, 425 청크)
- PDF 영수증 인덱싱 성공 (3개 파일, pypdf 폴백)
- 시맨틱 검색 동작 확인 ("쇼핑 행동 분석", "제주탐라짬뽕")

### MCP 서버 연결
- `claude mcp add nas-rag` 실행
- Claude Code 재시작 후 MCP 도구 7개 활성화 확인
- `get_stats`, `search_documents`, `search_excel` 실시간 동작 확인

### Session 4: OCR (M9)
- `image_parser.py`: EasyOCR 한국어+영어 (지연 로딩), 카테고리 추론
- indexer에 이미지 파서 등록
- EasyOCR + Pillow 설치
- 이미지 29개 전부 인덱싱 성공 (택시비, 식대, 접대비 영수증)

### NAS 전체 인덱싱
- `/Volumes/personal_folder` 하위 전체 인덱싱 실행
- 최종 결과: **66개 파일, 7,335 벡터 청크, 31 SQL 테이블**
  - Excel: 19개
  - PDF: 18개 (1개 이미지PDF 실패)
  - 이미지: 29개 (jpg, png)
- 야근 식대 총액 조회 테스트 성공: 18건, 201,850원

---

## 현재 상태

| 항목 | 상태 |
|------|------|
| Plan | ✅ 완료 |
| Design | ✅ 완료 |
| S1 Foundation | ✅ 완료 |
| S2 Parsers | ✅ 완료 |
| S3 Core | ✅ 완료 |
| S4 OCR | ✅ 완료 |
| S5 Agentic | ⏳ 미착수 |
| MCP 연결 | ✅ 동작 중 |
| NAS 전체 인덱싱 | ✅ 66파일/7,335청크 |

### 다음 작업
- `/pdca do nas-agentic-rag --scope agentic` — Agentic 라우터 (M6) 구현
- 영수증 구조화 추출 고도화 (날짜, 금액, 상호 필드 분리)
- 이미지 기반 PDF OCR 처리 (회사소개서 등)
