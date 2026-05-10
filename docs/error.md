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
