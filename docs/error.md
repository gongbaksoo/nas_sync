# Error Log

NAS Agentic RAG 구축 과정에서 발생한 에러와 해결 방법 기록.

---

## ERR-001: LanceDB NAS(SMB) 저장 실패

- **발생일**: 2026-05-10
- **증상**: `RuntimeError: lance error: LanceError(IO): Generic LocalFileSystem error: Unable to rename file: Operation not supported (os error 45)`
- **원인**: SMB(NAS 마운트)는 atomic rename 연산을 지원하지 않음. LanceDB의 Lance 포맷은 트랜잭션 시 atomic rename을 필수로 사용.
- **해결**: 인덱스 저장 경로를 NAS(`/Volumes/personal_folder/rag_db/`)에서 로컬(`~/.nas_rag/`)로 변경
- **영향 파일**: `mcp_rag_server/config.py`
- **교훈**: SMB/NFS 마운트 볼륨에서는 atomic file operation이 필요한 DB(LanceDB, SQLite WAL 등)를 사용할 수 없음. 로컬 저장 + NAS 원본 참조 패턴이 올바른 접근.

---

## ERR-002: Docling Python 3.14 미지원

- **발생일**: 2026-05-10
- **증상**: `ModuleNotFoundError: No module named 'docling'` — pip install docling 시 빌드 실패
- **원인**: Docling이 Python 3.14를 아직 지원하지 않음 (C 확장 모듈 빌드 실패)
- **해결**: pypdf를 폴백 파서로 사용. PdfParser에서 Docling 실패 시 자동으로 pypdf로 전환.
- **영향 파일**: `mcp_rag_server/parsers/pdf_parser.py`
- **한계**: pypdf는 이미지 기반 PDF(스캔 문서)에서 텍스트 추출 불가. 회사소개서 등 이미지 PDF는 인덱싱 실패.
- **향후**: Python 버전 업데이트 시 Docling 재시도, 또는 이미지 PDF용 OCR 파이프라인 추가

---

## ERR-003: PDF 파서 폴백 미동작

- **발생일**: 2026-05-10
- **증상**: pypdf 설치 후에도 PDF 인덱싱 실패. Docling 에러만 발생하고 pypdf 폴백이 실행되지 않음.
- **원인**: `_ensure_converter()` 호출이 try/except 블록 바깥에 있어서 ImportError가 catch되지 않음
- **해결**: `_ensure_converter()`를 try 블록 안으로 이동
- **영향 파일**: `mcp_rag_server/parsers/pdf_parser.py`
- **수정 전**:
  ```python
  self._ensure_converter()  # 여기서 ImportError 발생 -> catch 안됨
  try:
      result = self._converter.convert(file_path)
  except Exception as e:
      full_text = self._fallback_parse(file_path)
  ```
- **수정 후**:
  ```python
  try:
      self._ensure_converter()  # try 안으로 이동
      result = self._converter.convert(file_path)
  except Exception as e:
      full_text = self._fallback_parse(file_path)
  ```

---

## ERR-004: sync_to_nas.sh bash 산술 오류

- **발생일**: 2026-05-12
- **증상**: `syntax error in expression (error token is "0")` — Google Drive → sync 복사 단계에서 파일 카운트 계산 실패
- **원인**: `grep -c "^>" || echo "0"` 구문에서 grep 출력에 개행이 포함되어 `$((...))` 산술 연산이 파싱 실패
- **해결**: `grep -c "^>" || true`로 변경하여 grep이 0을 정상 반환하도록 수정
- **영향 파일**: `~/sync_to_nas.sh`
- **부수 영향**: ERR-004로 인해 초기 실행 시 Screen Shot 폴더(234개 파일) 동기화 누락. 수정 후 정상 복사 확인.

---

## ERR-005: launchd rsync Operation not permitted

- **발생일**: 2026-05-12
- **증상**: 터미널에서 수동 실행 시 정상이지만, launchd 자동 실행 시 `rsync: error: open /Users/j_mac_mini/Desktop/sync/: Operation not permitted` 발생 (exit code 23)
- **원인**: launchd가 `/bin/bash`를 통해 스크립트를 실행하는데, `/bin/bash`에 Full Disk Access 권한이 없어서 sync 폴더와 NAS 마운트 접근 불가
- **해결**: 시스템 설정 > 개인정보 및 보안 > Full Disk Access에 `/bin/bash` 추가
- **영향 파일**: `~/Library/LaunchAgents/com.sync.nas.plist` (설정 변경 없음, OS 권한 설정만 변경)
- **교훈**: macOS launchd에서 실행하는 프로세스는 터미널과 별도의 권한 컨텍스트를 가짐. 실행 바이너리(`/bin/bash`)에 직접 FDA 권한 부여 필요.
- **수정 전**:
  ```bash
  GDRIVE_COUNT=$((GDRIVE_COUNT + $(echo "$GDRIVE_OUT" | grep -c "^>" || echo "0")))
  ```
- **수정 후**:
  ```bash
  CNT=$(echo "$GDRIVE_OUT" | grep -c "^>" || true)
  GDRIVE_COUNT=$((GDRIVE_COUNT + CNT))
  ```

---

## ERR-006: rsync 전송 파일 카운트 항상 0

- **발생일**: 2026-05-14
- **증상**: 파일이 정상 복사되지만 로그에 "전송 파일: 0개"로 기록됨. Google Drive → sync 로그도 남지 않음 (카운트 0이면 로그 스킵)
- **원인**: `rsync -av` 출력은 파일명만 나열 (접두사 없음). `grep -c "^>"` 는 `rsync -i` (itemize-changes) 출력의 `>f........` 접두사를 기대하므로 항상 0
- **해결**: `rsync -av` → `rsync -avi`로 변경하여 itemize-changes 출력 활성화
- **영향 파일**: `~/sync_to_nas.sh` (3곳 모두 변경)
- **교훈**: rsync의 `-v`와 `-i` 출력 형식이 다름. 파일 카운트에는 `-i` 필수.

---

## ERR-007: rsync --exclude='~$*' 필터 미동작

- **발생일**: 2026-05-14
- **증상**: `--exclude='~$*'` 설정에도 Office 임시 파일(`~$260514_...xlsx`)이 동기화됨
- **원인**: rsync 필터는 **첫 번째 매칭 규칙 우선**. `--include='*.xlsx'`가 `--exclude='~$*'`보다 앞에 있어서 `~$xxx.xlsx`가 include에 먼저 매칭됨
- **해결**: `--exclude` 규칙을 `--include` 앞으로 이동
- **영향 파일**: `~/sync_to_nas.sh`
- **수정 전**:
  ```bash
  RSYNC_FILTERS=(
      --include='*.xlsx' ...
      --exclude='~$*' --exclude='.DS_Store' --exclude='Thumbs.db'
      --exclude='*'
  )
  ```
- **수정 후**:
  ```bash
  RSYNC_FILTERS=(
      --exclude='~$*' --exclude='.DS_Store' --exclude='Thumbs.db'
      --include='*.xlsx' ...
      --exclude='*'
  )
  ```
- **교훈**: rsync 필터는 순서가 중요. exclude를 먼저, include를 나중에 배치해야 의도대로 동작.

---

## ERR-008: xlsb/zip 확장자 누락으로 파일 미동기화

- **발생일**: 2026-05-15 (5/14 데이터 확인 중 발견)
- **증상**: Google Drive에 있는 `.xlsb`, `.zip` 파일이 sync 및 NAS에 동기화되지 않음. 5/14 오전 11시 이후 생성된 파일 다수 누락.
- **원인**: rsync 필터에 `.xlsb`, `.zip` 확장자가 포함되어 있지 않아 `--exclude='*'`에 의해 제외됨
- **해결**: `RSYNC_FILTERS`에 `--include='*.xlsb'`, `--include='*.zip'` 추가. 3단계 14일 삭제 find에도 동일 확장자 추가.
- **영향 파일**: `~/sync_to_nas.sh`
- **결과**: 수정 후 실행 시 88개 파일 NAS 전송 확인
- **교훈**: 사용자가 다루는 파일 형식을 사전에 파악하여 필터에 포함해야 함. 새로운 확장자가 등장할 수 있으므로 주기적 점검 필요.

---

## ERR-009: Google Drive File Provider mmap 오류로 날짜 폴더 누락

- **발생일**: 2026-05-19~2026-05-20
- **증상**:
  - 2026-05-19 `Download Backup/2026/2605/260519` 폴더가 Google Drive에는 존재하지만 로컬 `~/Desktop/sync`와 NAS에는 비어 있음
  - 2026-05-20 자동 실행 로그에 `Google Drive → sync 복사 (2개 파일)`이 반복되지만 NAS 전송은 `0개`
  - 로그에 `mmap: Resource deadlock avoided rsync_sender` 경고가 반복됨
- **원인**:
  - macOS Google Drive File Provider가 큰 `.xlsb` 파일 접근 중 mmap 오류를 내면서 전체 `Work Space` 트리 rsync가 일부 하위 날짜 폴더를 안정적으로 복사하지 못함
  - 기존 스크립트는 Google Drive rsync exit code를 치명 오류로 처리하지 않고 카운트만 기록해서 실제 누락이 `OK`처럼 보였음
- **해결**:
  - 5/19 누락 파일 수동 보강 후 로컬/NAS 각 15개 파일 확인
  - 5/20 누락 파일 수동 보강 후 로컬/NAS 각 2개 파일 확인
  - `sync_to_nas.sh`에서 당일 `Download Backup/YYYY/YYMM/YYMMDD` 폴더를 전체 `Work Space` 스캔보다 먼저 별도 복사하도록 변경
  - Google Drive rsync exit code와 `error/failed/cannot/denied` 문구를 WARN 로그로 기록
- **영향 파일**:
  - `~/sync_to_nas.sh`
  - `scripts/sync_to_nas.sh` (repository 보관용 사본)
  - `docs/01-plan/features/gdrive-to-sync.plan.md`
  - `NAS_동기화_인수인계.md`
- **검증**:
  - NAS dry-run 결과 `0`
  - 2026-05-20 `260520` 로컬/NAS 파일 수 각 `2`
- **교훈**: File Provider 기반 경로는 전체 트리 스캔을 신뢰하지 말고 업무상 중요한 날짜/신규 폴더는 좁은 범위로 우선 보강해야 함.

---

## ERR-010: Google Drive/rsync 장시간 대기 및 중복 실행 위험

- **발생일**: 2026-05-20
- **증상**:
  - 수동 실행 중 `Screen Shot` Google Drive rsync 단계가 장시간 멈춤
  - 자동 스케줄과 수동 실행이 겹칠 경우 이전 프로세스가 다음 실행을 밀어낼 가능성 확인
- **원인**:
  - Google Drive File Provider 응답 지연 시 rsync가 기본 설정으로 오래 대기할 수 있음
  - 기존 스크립트에 실행 lock이 없어 수동/자동 실행 중복을 명시적으로 막지 못함
- **해결**:
  - `GDRIVE_RSYNC_OPTS=(-avi --timeout=60)`
  - `NAS_RSYNC_OPTS=(-rlti --omit-dir-times --timeout=60)`
  - `~/.sync_nas.lock` 락 디렉토리 추가. 생성 실패 시 `SKIP: 이전 동기화 프로세스가 아직 실행 중` 기록 후 종료
  - `Screen Shot` rsync도 exit code 및 `timeout` 문구를 WARN 로그로 기록
- **영향 파일**:
  - `~/sync_to_nas.sh`
  - `scripts/sync_to_nas.sh`
  - `NAS_동기화_인수인계.md`
- **검증**:
  - 수정 후 수동 실행 정상 종료
  - `launchctl list`에서 `com.sync.nas` 로드 상태 확인
- **교훈**: launchd 주기 작업은 네트워크/클라우드 파일시스템 hang에 대비해 timeout과 lock을 기본으로 가져야 함.

---

## ERR-011: 대용량 RAG 인덱싱 진행상태 불투명 및 재시도 반복

- **발생일**: 2026-05-19~2026-05-20
- **증상**:
  - `260519_2.xlsx` 인덱싱이 27,660 청크에서 오래 걸리지만 진행률이 보이지 않음
  - 파싱 실패한 `.xls`와 빈 텍스트 PDF가 매 실행마다 반복 재시도됨
- **원인**:
  - 임베딩과 LanceDB 저장이 한 번에 처리되어 대용량 파일 진행상태를 알기 어려움
  - `auto_index.py`가 성공 파일만 마커에 저장하고 실패 파일 mtime은 기록하지 않음
- **해결**:
  - `EmbeddingEngine.encode()`를 512개 텍스트 단위로 나누고 `임베딩 진행: n/total` 로그 추가
  - `VectorStore.upsert()`를 1,000개 record 단위로 나누고 `청크 저장 진행: n/total` 로그 추가
  - `auto_index.py`에서 성공/실패/예외 모두 파일 mtime을 마커에 즉시 저장
  - 동기화 스크립트에서 RAG 인덱싱을 백그라운드 실행하고 중복 실행 시 skip
- **영향 파일**:
  - `mcp_rag_server/auto_index.py`
  - `mcp_rag_server/embeddings.py`
  - `mcp_rag_server/stores/vector_store.py`
  - `~/sync_to_nas.sh`
- **검증**:
  - 5/19 변경분 인덱싱: `10 성공, 19 실패`; `260519_2.xlsx` 27,660 청크 성공
  - 5/20 변경분 인덱싱: `45 성공, 0 실패`
  - 재실행 시 `변경된 파일 없음 — 인덱싱 건너뜀`
- **교훈**: 장시간 배치 작업은 파일 단위 체크포인트와 청크 단위 진행 로그가 있어야 운영 중단/재시도 비용을 통제할 수 있음.
