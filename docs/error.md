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
