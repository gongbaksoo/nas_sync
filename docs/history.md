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

## 2026-05-12: Google Drive → sync 자동 동기화

### Plan Plus
- 맥북 Google Drive '내 Mac' 폴더를 Mac Mini sync 폴더로 자동 연동하는 요구사항 분석
- Phase 0~5 수행: 컨텍스트 탐색 → Intent Discovery → 대안 탐색 → YAGNI → 설계 검증 → Plan 문서 생성
- 핵심 발견: 맥북/Mac Mini 모두 Google Drive 설치됨 → Mac Mini 내부 로컬 복사만 필요
- Plan 문서: `docs/01-plan/features/gdrive-to-sync.plan.md`

### 구현
- `~/sync_to_nas.sh` 수정: 0단계(Google Drive → sync) 추가
  - 소스: `~/Library/CloudStorage/GoogleDrive-gongbaksoo@gmail.com/다른 컴퓨터/내 Mac/`
  - Work Space/ → ~/Desktop/sync/, Screen Shot/ → ~/Desktop/sync/Screen Shot/
- rsync 필터를 공통 `RSYNC_FILTERS` 배열 변수로 리팩토링
- 기존 launchd 스케줄(매시 정각) 변경 없이 자동 실행

### 트러블슈팅
- **ERR-004**: bash 산술 오류 — `grep -c` 출력 개행 문제 → 변수 분리로 해결
- **Full Disk Access**: rsync 권한 문제 → 시스템 설정에서 권한 추가로 해결
- **Screen Shot 동기화 누락**: ERR-004로 인해 초기 실행 시 Screen Shot 복사 단계 미실행 → 수정 후 234개 파일 정상 복사 확인
- **ERR-005**: launchd rsync 권한 오류 — `/bin/bash`에 Full Disk Access 권한 없음 → 시스템 설정에서 FDA 추가로 해결
- **ERR-006**: rsync 전송 카운트 항상 0 — `-av`에서 `grep "^>"` 불일치 → `-avi`로 변경하여 해결
- **ERR-007**: `~$` Office 임시 파일 제외 안 됨 — rsync 필터 순서 문제 → `--exclude`를 `--include` 앞으로 이동

### 테스트 결과
- dry-run: 805개 파일(Work Space) + 234개 파일(Screen Shot) 대상 확인
- 실제 실행: exit code 0, Google Drive → sync 663개, sync → NAS 3개 전송 로그 정상
- NAS 도착 확인: Screen Shot 234개, AVK/Download Backup/Stock Data 전체 복사됨
- `~$` 임시 파일 필터링 정상 동작 확인
- 파이프라인: 맥북 → Google Drive → Mac Mini sync → NAS

---

## 2026-05-15: xlsb/zip 확장자 추가

### 이슈
- 5/14 오전 11시 이후 생성된 `.xlsb`, `.zip` 파일이 NAS에 동기화되지 않음 발견
- 원인: rsync 필터에 해당 확장자 미포함 (ERR-008)

### 수정
- `sync_to_nas.sh` RSYNC_FILTERS에 `--include='*.xlsb'`, `--include='*.zip'` 추가
- 3단계 14일 삭제 find에도 동일 확장자 추가

### 결과
- 수정 후 실행: Google Drive → sync 773개, sync → NAS 88개 전송
- 누락됐던 xlsb 5개, zip 5개, jpg 1개, xlsx 1개 NAS 도착 확인

---

## 2026-05-20: 5/19 수동 보강분 확인 및 RAG 인덱싱 개선

### 이슈
- 2026-05-19 `Download Backup/2026/2605/260519` 폴더가 Google Drive에는 있었지만 로컬/NAS에는 비어 있던 문제 확인
- Google Drive 전체 `Work Space` rsync는 실행됐지만 NAS 전송 파일 수가 `0개`로 남음
- 5/18 수동 싱크분 중 일부 오래된 `.xls` 실패 파일이 매번 재시도됨
- 대용량 `260519_2.xlsx`는 27,660 청크 인덱싱 중 진행상태가 보이지 않아 운영 판단이 어려움

### 조치
- 5/19 누락 파일을 수동 보강하여 로컬/NAS 각 15개 파일 확인
- `csv`, `html`, `htm` 확장자를 rsync 필터와 14일 삭제 대상에 추가
- `auto_index.py`에서 성공/실패/예외 모두 파일 mtime을 마커에 저장하도록 수정
- `embeddings.py`에 512개 단위 임베딩 진행 로그 추가
- `vector_store.py`에 1,000개 단위 LanceDB 저장 진행 로그 추가
- RAG 인덱싱을 동기화 스크립트에서 백그라운드 실행하도록 전환

### 결과
- 5/18 마커: 기존 성공분과 실패 처리된 `.xls` 포함 47개 기록
- 5/19 마커: 12개 기록 (성공 10개 + 빈 텍스트 PDF 실패 2개)
- `260519_2.xlsx`: 27,660 청크 인덱싱 성공
- 재실행 확인: `변경된 파일 없음 — 인덱싱 건너뜀`

---

## 2026-05-20: 5/20 동기화 장애 재발 대응

### 이슈
- 자동 스케줄은 매시 실행되고 있었지만 오늘 `260520` 폴더가 로컬/NAS에 비어 있음
- 로그에 5/19 큰 `.xlsb` 파일 관련 `mmap: Resource deadlock avoided`가 반복됨
- 수동 실행 중 `Screen Shot` Google Drive rsync가 장시간 대기하는 상태 확인

### 조치
- 5/20 오늘 파일 2개를 수동 보강하여 로컬/NAS로 복사
- `sync_to_nas.sh`에서 당일 `Download Backup/YYYY/YYMM/YYMMDD` 폴더를 전체 `Work Space` 스캔보다 먼저 복사하도록 순서 변경
- Google Drive/NAS rsync에 `--timeout=60` 추가
- `~/.sync_nas.lock` 기반 중복 실행 방지 추가
- Google Drive rsync exit code와 timeout/error 문구를 WARN 로그에 남기도록 개선
- repository 추적을 위해 운영 스크립트 사본 `scripts/sync_to_nas.sh` 추가
- SOP/Plan 문서와 error/history 문서 갱신

### 검증
- 로컬 `260520`: 2개 파일
- NAS `260520`: 2개 파일
- NAS dry-run: 0
- RAG 인덱싱: 45 성공, 0 실패
- 재실행 확인: `변경된 파일 없음 — 인덱싱 건너뜀`
- launchd: `com.sync.nas` 로드 상태 정상

---

## 2026-05-21: rclone 기반 Google Drive API 동기화 도입

### 이슈
- 5/21 자동 실행이 정상 동작했지만 `260521` 오늘 폴더가 로컬/NAS에 비어 있음
- Google Drive File Provider 경로에서 `mmap: Resource deadlock avoided`가 계속 재발
- File Provider 기반 `rsync`/복사 보강만으로는 날짜 폴더 누락을 안정적으로 막기 어려움

### 조치
- rclone 1.74.1 설치
- Google Drive 로컬 xattr에서 `Work Space` 폴더 ID `15FxOAg39qbr7jLOtEMceEyFXJ34H24TW` 확인
- Google Drive 로컬 xattr에서 `Screen Shot` 폴더 ID `1rPE71JlLqAcq1BNZI5kE8mKwo0-2hCpf` 확인
- Google Drive connector로 해당 ID가 `Work Space` 폴더임을 검증
- `sync_to_nas.sh`에 rclone 당일 폴더 및 Screen Shot 우선 복사 로직 추가
- rclone 미설정/실패 시 기존 File Provider `cp -p` fallback 유지
- `gdrive-rclone-sync.design.md` 신규 작성

### 검증 기준
- `rclone lsf gdrive_nas:"Download Backup/YYYY/YYMM/YYMMDD"`로 API 기준 파일 수 확인
- `~/sync_to_nas.sh` 수동 실행 후 로컬/NAS 파일 수 비교
- NAS dry-run 0 확인
- RAG 인덱싱 재실행 시 변경 없음 확인

---

## 2026-05-22: launchd rclone PATH 보정 및 10시/11시 검증

### 이슈
- 07~09시 정기 실행에서 `rclone 미설치` 경고가 반복됨
- rclone은 `/opt/homebrew/bin/rclone`에 설치되어 있었지만 launchd 환경 PATH에 Homebrew 경로가 없어 탐색 실패
- File Provider fallback으로 떨어진 Screen Shot 복사에서 `Resource deadlock avoided`가 다시 발생

### 조치
- `sync_to_nas.sh` 시작부에 `/opt/homebrew/bin:/usr/local/bin` PATH 보정 추가
- `find_rclone()`을 추가하여 `command -v rclone` 실패 시 `/opt/homebrew/bin/rclone`, `/usr/local/bin/rclone`을 직접 확인
- 운영 스크립트(`~/sync_to_nas.sh`)와 repository 사본(`scripts/sync_to_nas.sh`) 모두 동일하게 수정
- plan/design/error/history 문서에 5/22 운영 이슈와 검증 결과 반영

### 검증
- `bash -n ~/sync_to_nas.sh`, `bash -n scripts/sync_to_nas.sh` 통과
- 수동 실행 후 `260522` 당일 폴더 local/NAS 각 23개 확인
- NAS dry-run 0 확인
- 수동 RAG 인덱싱: 31개 변경 감지, 16 성공, 15 실패
- RAG 재실행: `변경된 파일 없음 — 인덱싱 건너뜀`
- 10:00 정기 실행: rclone 당일 폴더 0개 증가, Screen Shot 6개 증가, NAS 전송 6개
- 11:00 정기 실행: rclone 당일 폴더 0개 증가, Screen Shot 0개 증가, NAS 전송 0개
- 10시/11시 로그에서 `rclone 미설치`와 `Resource deadlock avoided` 재발 없음

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
| NAS 전체 인덱싱 | ✅ 동작 중 (`~/.nas_rag`) |
| Google Drive → sync | ✅ 완료 (xlsb/zip/csv/html 포함, 당일 폴더 우선 보강) |
| Google Drive API 동기화 | ✅ rclone primary + File Provider fallback 구조 |
| RAG 자동 인덱싱 | ✅ 백그라운드 실행, 실패 파일 마커 기록 |
| 동기화 안전장치 | ✅ timeout 60초, lock, WARN 로깅, launchd PATH 보정 |

### 다음 작업
- `/pdca do nas-agentic-rag --scope agentic` — Agentic 라우터 (M6) 구현
- 영수증 구조화 추출 고도화 (날짜, 금액, 상호 필드 분리)
- 이미지 기반 PDF OCR 처리 (회사소개서 등)
