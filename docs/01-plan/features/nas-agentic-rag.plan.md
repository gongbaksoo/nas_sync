# NAS Agentic RAG 시스템 구축 Plan

> 생성일: 2026-05-09
> Phase: Plan (Plan Plus)
> 이전 단계: nas-sync.plan.md (동기화 시스템 완료)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | NAS에 동기화된 파일(Excel, PDF, 이미지)을 자연어로 검색하거나 내용을 분석할 수 없음. 파일을 찾으려면 직접 폴더를 탐색해야 함 |
| **Solution** | Claude Code에서 MCP 프로토콜로 연결되는 커스텀 RAG 서버를 구축하여, 자연어 질의로 NAS 파일을 검색하고 내용을 분석 |
| **기능/UX 효과** | "매출보고서 찾아줘", "지난달 택시비 총액은?" 같은 자연어로 즉시 파일 검색 + 내용 분석. Agentic 라우팅으로 최적 검색 전략 자동 선택 |
| **Core Value** | 개인 NAS를 AI 지식 베이스로 전환. 파일 관리에서 지식 활용으로 패러다임 전환 |

---

## 1. User Intent Discovery

### 1.1 Core Problem
NAS에 동기화된 다양한 파일(Excel 마케팅/판매 분석, PDF 경비영수증/회사소개서, 상품 이미지)을 자연어로 검색하고 내용까지 분석하는 풀 RAG 시스템이 필요함.

### 1.2 Target Users
- 주 사용자: Mac Mini에서 Claude Code를 사용하는 본인
- 사용 방식: Claude Code에서 직접 MCP 도구로 호출

### 1.3 Success Criteria
- Claude Code에서 "매출보고서 찾아줘"로 NAS 파일 검색 가능
- Excel 데이터에 대해 "지난달 마케팅 채널별 유입 현황은?" 같은 수치 질의 응답 가능
- 영수증 이미지에서 "이번달 택시비 총액은?" 같은 OCR 기반 검색 가능
- 쿼리 의도에 따라 최적 검색 전략을 자동 선택하는 Agentic 라우팅

### 1.4 Constraints
- Mac Mini 리소스 내에서 동작 (로컬 임베딩 모델 ~2GB)
- NAS 네트워크 지연 고려 (Wi-Fi 연결)
- 한국어 문서가 주 대상
- 외부 API 의존 최소화 (프라이버시 + 비용)

---

## 2. Alternatives Explored

### 2.1 Approach A: 커스텀 MCP RAG 서버 (선택됨)
- **Pros**: NAS 환경 100% 맞춤, Excel/한국어/이미지 모두 지원, Agentic RAG 확장 용이
- **Cons**: 초기 개발 시간 필요
- **선택 이유**: 장기적 유용성이 가장 중요하다는 사용자 판단

### 2.2 Approach B: 기존 MCP RAG 서버 (mcp-local-rag)
- **Pros**: 설치 1줄, 즉시 사용
- **Cons**: Excel 미지원, 한국어 최적화 없음, 확장성 제한
- **불채택 이유**: 요구 범위 미충족

### 2.3 Approach C: 하이브리드
- **Pros**: 빠른 검증 + 장기 확장
- **Cons**: 중간 시스템 교체, 인덱스 재구축
- **불채택 이유**: 어차피 커스텀 필요하므로 처음부터 구축

---

## 3. YAGNI Review

### 3.1 포함 (MVP)
- [x] PDF 문서 시맨틱 검색
- [x] Excel 하이브리드 검색 (벡터 + SQL)
- [x] 이미지/영수증 OCR 검색
- [x] Agentic 라우팅 + Self-reflection
- [x] MCP 서버 Claude Code 통합
- [x] 한국어 최적화 임베딩

### 3.2 제외 (Out of Scope)
- [ ] 웹 UI / Chatbot 인터페이스
- [ ] REST API 서버
- [ ] 네이티브 멀티모달 임베딩 (CLIP)
- [ ] Multi-Agent 시스템 (코디네이터 + 전문 에이전트 분리)
- [ ] 자동 파일 변경 감지 (watchdog) — 수동 인덱싱으로 시작
- [ ] 대용량 초기 마이그레이션 도구

---

## 4. Architecture

### 4.1 전체 아키텍처

```
┌────────────────────────────────────────────────────┐
│                    Claude Code                      │
│           (사용자: "매출보고서 찾아줘")              │
└───────────────┬────────────────────────────────────┘
                │ MCP stdio
                ▼
┌────────────────────────────────────────────────────┐
│          NAS RAG MCP 서버 (Python)                 │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │     Agentic Router                           │   │
│  │     쿼리 의도 분석 → 검색 전략 선택          │   │
│  │     Self-reflection → 결과 품질 평가         │   │
│  └──────────┬──────────┬──────────┬─────────────┘   │
│             │          │          │                   │
│      ┌──────▼──┐ ┌─────▼────┐ ┌──▼─────────┐       │
│      │ 문서    │ │ Excel    │ │ 이미지     │        │
│      │ 검색    │ │ 수치검색 │ │ OCR 검색   │        │
│      │ (벡터)  │ │(하이브리드)│ │(텍스트변환)│        │
│      └──────┬──┘ └─────┬────┘ └──┬─────────┘       │
│             │          │          │                   │
│  ┌──────────▼──────────▼──────────▼─────────────┐   │
│  │              인덱싱 엔진                      │   │
│  │  Docling(PDF) + pandas(Excel) + EasyOCR(img)  │   │
│  │  → BGE-m3-ko 임베딩 → LanceDB 저장           │   │
│  │  → DuckDB (Excel 수치 보조 인덱스)            │   │
│  └──────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────┐
│          NAS (/Volumes/personal_folder/)            │
│  ├── Macmini_backup/  (동기화된 파일 원본)         │
│  └── rag_db/          (LanceDB + DuckDB 인덱스)    │
└────────────────────────────────────────────────────┘
```

### 4.2 기술 스택

| 구성요소 | 기술 | 선택 근거 |
|----------|------|-----------|
| 벡터 DB | **LanceDB** | 서버리스/임베디드, Docker 불필요, NAS 경로 직접 사용, 디스크 네이티브 |
| 임베딩 모델 | **BGE-m3-ko** (또는 upskyy/bge-m3-korean) | 한국어 파인튜닝, 로컬 실행, 무료, 1024차원, 8192 토큰 |
| 문서 파싱 | **Docling** (IBM) | 테이블 인식 94%+, 완전 로컬, 무료 오픈소스 |
| Excel 파싱 | **pandas** + openpyxl/xlrd/read_html fallback | 시트/테이블 단위 청킹, 요약 통계 자동 생성, HTML-export `.xls` 대응 |
| OCR | **EasyOCR** | 한국어 지원, 설치 간편 |
| 보조 DB | **DuckDB** | Excel 수치 검색용, 임베디드, SQL 지원 |
| 한국어 처리 | **Kiwi** (형태소 분석) + **KSS** (문장 분리) | 한국어 교착어 특성 대응 |
| MCP 프레임워크 | **mcp Python SDK** | Claude Code 네이티브 통합 |

### 4.3 프로젝트 구조

```
nas_sync/
├── mcp_rag_server/
│   ├── server.py              # MCP 서버 엔트리포인트
│   ├── config.py              # 설정 (경로, 모델명 등)
│   ├── indexer.py             # 인덱싱 오케스트레이터
│   ├── searcher.py            # 검색 오케스트레이터
│   ├── agentic_router.py      # Agentic 라우팅 + Self-reflection
│   ├── embeddings.py          # BGE-m3-ko 임베딩 래퍼
│   ├── parsers/
│   │   ├── pdf_parser.py      # Docling 기반 PDF 파싱
│   │   ├── excel_parser.py    # pandas + Docling Excel 파싱
│   │   └── image_parser.py    # EasyOCR 이미지/영수증 파싱
│   ├── stores/
│   │   ├── vector_store.py    # LanceDB 래퍼
│   │   └── sql_store.py       # DuckDB 래퍼 (Excel 수치)
│   └── utils/
│       └── korean.py          # Kiwi + KSS 한국어 처리
├── tests/
│   ├── test_parsers.py
│   ├── test_search.py
│   └── test_integration.py
├── docs/
│   └── 01-plan/features/
│       └── nas-agentic-rag.plan.md  # 이 문서
└── Agentic_RAG_구축_실전_가이드.md   # 리서치 레퍼런스
```

---

## 5. MCP Tool Interface

### 5.1 도구 목록

| 도구명 | 설명 | 파라미터 | Phase |
|--------|------|----------|-------|
| `search_documents` | PDF/텍스트 시맨틱 검색 | query, top_k, file_type | 1 |
| `search_excel` | Excel 하이브리드 검색 | query, sheet_name, sql_filter | 1 |
| `search_receipts` | 영수증/이미지 OCR 검색 | query, date_range, amount_range | 2 |
| `index_file` | 단일 파일 인덱싱 | file_path | 1 |
| `index_directory` | 디렉토리 일괄 인덱싱 | dir_path, recursive, file_types | 1 |
| `get_file_content` | 인덱싱된 파일 원본 내용 조회 | file_path, page/sheet | 1 |
| `get_stats` | 인덱싱 현황/통계 | — | 1 |
| `smart_search` | Agentic 라우터 (의도→자동 라우팅) | query | 3 |

### 5.2 도구 상세 설계

#### search_documents
```python
@mcp_tool
def search_documents(query: str, top_k: int = 5, file_type: str = None) -> list:
    """NAS 문서에서 시맨틱 검색

    Args:
        query: 자연어 검색 쿼리 (예: "회사소개서에서 주요 제품 찾아줘")
        top_k: 반환할 결과 수 (기본 5)
        file_type: 필터링할 파일 타입 (pdf, excel, image, None=전체)

    Returns:
        [{text, score, source_file, page/sheet, metadata}]
    """
```

#### search_excel
```python
@mcp_tool
def search_excel(query: str, sheet_name: str = None, sql_filter: str = None) -> list:
    """Excel 파일 하이브리드 검색 (시맨틱 + SQL)

    Args:
        query: 자연어 쿼리 (예: "마케팅 채널별 유입 현황")
        sheet_name: 특정 시트명 필터 (선택)
        sql_filter: SQL 조건 (예: "매출 > 1000000") (선택)

    Returns:
        [{text, score, source_file, sheet, columns, summary, metadata}]
    """
```

#### smart_search (Agentic)
```python
@mcp_tool
def smart_search(query: str) -> dict:
    """Agentic RAG: 쿼리 의도를 분석하여 최적 검색 전략 자동 선택

    내부 로직:
    1. 쿼리 의도 분류 (문서검색 / 수치분석 / 영수증 / 복합)
    2. 적절한 검색 도구 선택 & 실행
    3. Self-reflection: 결과 품질 평가
    4. 불충분하면 쿼리 재구성 후 재검색
    5. 최종 결과 + 출처 반환

    Args:
        query: 자연어 질의

    Returns:
        {results, search_strategy_used, confidence, sources}
    """
```

---

## 6. Data Flow

### 6.1 인덱싱 파이프라인

```
NAS 파일 → 파일 타입 감지 → 파서 선택 → 청킹 → 임베딩 → 저장

PDF:    Docling → 시맨틱 청킹 (512-1024 토큰, 50-100 오버랩) → BGE-m3-ko → LanceDB
Excel:  파일 시그니처 판별 → pandas(openpyxl/xlrd/read_html/csv fallback) → 시트 요약 + 테이블 단위 청킹 (헤더 항상 포함) → BGE-m3-ko → LanceDB + DuckDB
이미지: EasyOCR → OCR 텍스트 + 메타데이터 → BGE-m3-ko → LanceDB
```

### 6.2 청킹 전략

| 문서 타입 | 청킹 전략 | 청크 크기 | 오버랩 | 비고 |
|-----------|----------|----------|--------|------|
| PDF (텍스트) | 시맨틱 청킹 (KSS) | 512-1024 토큰 | 50-100 토큰 | 한국어 문장 분리기 사용 |
| PDF (영수증) | 문서 단위 (1건=1청크) | 전체 | 없음 | OCR 결과 전체를 하나로 |
| Excel (분석) | 시트 요약 + 행 그룹 | 15-20행 그룹 | 헤더 항상 포함 | 수치 요약 별도 청크 |
| 이미지 | 메타데이터 + OCR 텍스트 | 가변 | 없음 | 폴더명=카테고리 힌트 |

### 6.3 메타데이터 스키마

모든 청크에 다음 메타데이터를 첨부:

```python
{
    "source_file": "/Volumes/personal_folder/Macmini_backup/...",
    "file_name": "매출보고서.xlsx",
    "file_type": "excel",          # pdf, excel, image
    "chunk_id": "매출보고서_Sheet1_0-15",
    "page_or_sheet": "Sheet1",
    "date_created": "2026-05-08",
    "date_indexed": "2026-05-09T09:00:00",
    "size_bytes": 24500,
    "language": "ko",
    # Excel 전용
    "columns": ["채널", "유입수", "전환율"],
    "row_range": "0-15",
    # 이미지 전용
    "ocr_text": "...",
    "resolution": "1920x1080"
}
```

### 6.4 검색 전략

| 검색 유형 | 메서드 | 사용 시점 |
|-----------|--------|-----------|
| 벡터 검색 | LanceDB 시맨틱 유사도 | "회사소개서에서 제품 설명" |
| 키워드 검색 | LanceDB 풀텍스트 + Kiwi 형태소 | "콧물흡입기 견적서" |
| SQL 검색 | DuckDB 직접 쿼리 | "매출 > 100만원인 채널" |
| 하이브리드 | 벡터 + 키워드 + SQL 결합 | "마케팅 채널별 유입 현황" |
| Agentic | 의도 분석 → 자동 선택 | smart_search 도구 |

---

## 7. Implementation Roadmap

### Phase 1: 기본 RAG (PDF + Excel) — ✅ 완료 (2026-05-10)

**목표**: PDF/Excel 파일에 대한 기본 시맨틱 + 하이브리드 검색

**태스크**:
1. ✅ Python 프로젝트 초기화 (venv, dependencies)
2. ✅ LanceDB + BGE-m3-ko 설치 및 기본 구성
3. ✅ PDF 파싱 파이프라인 (pypdf 폴백 — Docling은 Python 3.14 미지원)
4. ✅ Excel 파싱 파이프라인 (pandas + 테이블 단위 청킹)
5. ✅ 임베딩 엔진 (BGE-m3-ko 래퍼, MPS GPU 지원)
6. ✅ 벡터 스토어 (LanceDB 래퍼 — 로컬 저장 `~/.nas_rag/`)
7. ✅ SQL 스토어 (DuckDB, Excel 수치용)
8. ✅ MCP 서버 (search_documents, search_excel, index_file, index_directory, get_stats, get_file_content, search_receipts)
9. ✅ Claude Code MCP 연결 설정 (`claude mcp add nas-rag`)
10. ✅ 실제 NAS 파일로 테스트 (Excel 19개 + PDF 18개 인덱싱 성공)

### Phase 2: 이미지/영수증 OCR — ✅ 완료 (2026-05-10)

**목표**: 이미지/영수증 파일 OCR + 검색

**태스크**:
1. ✅ EasyOCR 설치 및 한국어 모델 설정
2. ✅ 이미지/영수증 파싱 파이프라인 (image_parser.py)
3. ⏳ 영수증 구조화 추출 (날짜, 금액, 상호) — 현재 OCR 텍스트 전체 저장, 구조화 미완
4. ✅ search_receipts MCP 도구 추가
5. ✅ 실제 영수증/상품사진 29개 인덱싱 + 검색 테스트 성공

### Phase 3: Agentic RAG — ⏳ 미착수

**목표**: 자율적 검색 전략 선택 + 자기 반성

**태스크**:
1. ⏳ 쿼리 의도 분류기 구현 (문서/수치/영수증/복합)
2. ⏳ Agentic 라우터 구현 (의도 → 도구 선택)
3. ⏳ Self-reflection 패턴 (결과 품질 자체 평가 → 재검색)
4. ⏳ smart_search MCP 도구 추가
5. ⏳ 복합 시나리오 통합 테스트
6. ⏳ CLAUDE.md에 RAG 도구 사용 가이드 추가

---

## 8. Risk & Mitigation

| 리스크 | 확률 | 영향 | 대응 | 실제 결과 |
|--------|------|------|------|-----------|
| Mac Mini 리소스 부족 (BGE-m3-ko ~2GB) | 낮음 | 높음 | M 시리즈 칩은 충분 | ✅ 문제없음 |
| NAS 네트워크 I/O 지연 | 중간 | 중간 | 벡터 DB를 로컬에 저장 | ✅ **실제 발생** — SMB atomic rename 미지원으로 LanceDB NAS 저장 불가. `~/.nas_rag/`로 변경 |
| 한국어 임베딩 품질 | 중간 | 중간 | BGE-m3-ko 테스트 | ✅ 검색 동작 확인, 추가 튜닝 필요 |
| Excel 테이블 구조 다양성 | 높음 | 중간 | 청킹 전략 커스터마이징 | ✅ 시트 요약 + 행 그룹 청킹, HTML-export `.xls` fallback 적용 |
| `.xls` 확장자와 실제 파일 형식 불일치 | 높음 | 중간 | 파일 헤더 기반 로더 분기 | ✅ CFB Excel, HTML table, CSV fallback 처리 |

## 10. 운영 보강 이력

- **2026-05-23 `.xls` 인덱싱 보강**: `.xls` 파일 헤더를 확인해 진짜 BIFF Excel은 `xlrd>=2.0.1`, HTML table export는 `pandas.read_html`, 불명확한 파일은 Excel/HTML/CSV 순서 fallback으로 처리한다. DuckDB 테이블명에는 해시 suffix를 붙여 긴 한글 파일명의 테이블명 충돌을 방지한다.
| Docling 설치 복잡도 | 낮음 | 낮음 | pypdf 대체 | ✅ **실제 발생** — Python 3.14 미지원. pypdf 폴백 적용 |

---

## 9. Brainstorming Log

| 단계 | 질문 | 결정 | 근거 |
|------|------|------|------|
| Phase 1 Q1 | RAG 핵심 목적 | 파일 검색 + 내용 분석 모두 | 풀 RAG 필요 |
| Phase 1 Q2 | 사용 방식 | Claude Code에서 직접 | 별도 UI 불필요, MCP 통합 |
| Phase 1 Q3 | 분석 수준 | 심층 리서치 후 결정 | Agentic RAG까지 원함, 장기적 유용성 중시 |
| Phase 2 | 아키텍처 | 커스텀 MCP RAG 서버 | 장기적 확장성, NAS 맞춤 |
| Phase 3 | MVP 범위 | 전 기능 포함 (3단계 구현) | 사용자 선택 |
| Phase 4-1 | 전체 아키텍처 | 승인 | — |
| Phase 4-2 | 도구 구성 (8개) | 승인 | — |
| Phase 4-3 | 데이터 흐름 | 승인 | — |

---

## 10. Research References

리서치 상세 내용: `Agentic_RAG_구축_실전_가이드.md`

### 핵심 레퍼런스
- [Agentic RAG Survey - arXiv](https://arxiv.org/abs/2501.09136)
- [RAG Best Practices from 100+ Teams - kapa.ai](https://www.kapa.ai/blog/rag-best-practices)
- [LanceDB Documentation](https://docs.lancedb.com/quickstart)
- [BGE-m3-ko - HuggingFace](https://huggingface.co/dragonkue/BGE-m3-ko)
- [Docling vs LlamaParse vs Unstructured](https://boringbot.substack.com/p/pdf-table-extraction-showdown-docling)
- [mcp-local-rag - GitHub](https://github.com/shinpr/mcp-local-rag)
- [claude-code-helper RAG MCP Guide](https://github.com/michelabboud/claude-code-helper/blob/main/guides/RAG-MCP-GUIDE.md)

---

## Next Step

```
/pdca do nas-agentic-rag --scope agentic
```
