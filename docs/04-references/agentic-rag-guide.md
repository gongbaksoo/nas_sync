# Agentic RAG 구축 실전 가이드

> 조사일: 2026-05-09
> 대상 환경: Mac Mini + UGREEN NAS + Claude Code
> 대상 파일: Excel(마케팅/판매분석), PDF(경비영수증, 회사소개서), 이미지(상품사진, 영수증)

---

## 목차

1. [RAG 실전 경험담 및 교훈](#1-rag-실전-경험담-및-교훈)
2. [Agentic RAG 아키텍처 패턴](#2-agentic-rag-아키텍처-패턴)
3. [로컬/NAS 파일 시스템 RAG 스택](#3-로컬nas-파일-시스템-rag-스택)
4. [Claude Code/MCP 통합 패턴](#4-claude-codemcp-통합-패턴)
5. [비정형 데이터(Excel, 이미지, 한국어) RAG](#5-비정형-데이터excel-이미지-한국어-rag)
6. [추천 아키텍처 및 구현 로드맵](#6-추천-아키텍처-및-구현-로드맵)

---

## 1. RAG 실전 경험담 및 교훈

### 1.1 핵심 발견사항

#### 가장 흔한 실수 TOP 7

| 순위 | 실수 | 영향 | 해결 방법 |
|------|------|------|-----------|
| 1 | **데이터 품질 무시** | RAG 실패의 42% 원인 (2024 설문) | 투입 전 데이터 정제 파이프라인 구축 |
| 2 | **청크 크기 부적절** | 너무 작으면(200토큰) 문맥 소실, 너무 크면 노이즈 | 512토큰 + 50토큰 오버랩으로 시작, 반복 실험 |
| 3 | **청크 오버랩 과다** | 중복 컨텍스트 → 프롬프트 비용 증가 | 15% 오버랩 권장 |
| 4 | **출처 메타데이터 미저장** | 디버깅/인용 불가 | 파일명, 페이지, 청크ID 반드시 저장 |
| 5 | **모니터링 미구축** | 품질 저하 감지 불가 | 초기부터 평가 지표 설정 |
| 6 | **전체 데이터 무분별 투입** | 노이즈 증가, 검색 정확도 하락 | 핵심 소스부터 시작, 점진 확장 |
| 7 | **단일 검색 방법 의존** | 검색 누락 발생 | 하이브리드 검색(벡터 + 키워드 + 풀텍스트) |

#### 100+ 팀의 베스트 프랙티스 (kapa.ai 조사)

1. **핵심 소스부터 시작**: 기술 문서, API 레퍼런스, 검증된 지원 문서 먼저 인덱싱
2. **민감/공개 데이터 분리**: 별도 벡터 스토어로 관리
3. **증분 업데이트**: 전체 재인덱싱 대신 Git diff 방식의 델타 처리
4. **근거 기반 응답**: 반드시 인용 포함, 컨텍스트 외 정보는 "모른다"고 답변
5. **도메인별 평가**: 범용 벤치마크 대신 실제 사용자 질의 기반 평가

#### 핵심 교훈

- **"RAG는 모델을 똑똑하게 만드는 것이 아니라, 더 좋은 정보를 주는 것"**
- 벡터 DB 선택은 전체 RAG 품질의 5-10%에 불과. **청킹 전략, 임베딩 모델, 검색 파이프라인이 훨씬 중요**
- IBM Research: 벡터 검색 + 스파스 벡터 + 풀텍스트 검색 조합이 최적 리콜 달성
- 할루시네이션 방지: "제공된 컨텍스트만 사용하라"는 명시적 프롬프트 필수

### 1.2 출처

- [RAG Best Practices: Lessons from 100+ Technical Teams - kapa.ai](https://www.kapa.ai/blog/rag-best-practices)
- [Six Lessons Learned Building RAG Systems in Production - Towards Data Science](https://towardsdatascience.com/six-lessons-learned-building-rag-systems-in-production/)
- [Building Production-Ready RAG Systems - Medium](https://medium.com/@meeran03/building-production-ready-rag-systems-best-practices-and-latest-tools-581cae9518e7)
- [Build a local RAG system - NetMentor](https://www.netmentor.es/entrada/en/building-local-rag)
- [From RAG to Context - RAGFlow 2025 Review](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)

### 1.3 우리 프로젝트 적용 시사점

- NAS의 파일은 종류가 다양하므로 **파일 타입별 청킹 전략**을 별도로 설계해야 함
- Excel(마케팅/판매)은 구조화 데이터 → 테이블 인식 청킹 필요
- PDF(영수증)는 OCR + 메타데이터 추출이 관건
- 초기에는 **회사소개서 PDF와 Excel 분석 파일**부터 시작, 이미지는 나중에 추가
- 출처 메타데이터(파일경로, 시트명, 페이지번호)를 반드시 함께 저장

---

## 2. Agentic RAG 아키텍처 패턴

### 2.1 기본 RAG vs Agentic RAG 비교

| 차원 | 기본 RAG | Agentic RAG |
|------|---------|-------------|
| **적응성** | 최소 (고정 파이프라인) | 쿼리 기반 동적 전략 선택 |
| **컨텍스트 유지** | 제한적 | 상호작용 간 지속적 메모리 |
| **추론 능력** | 단일 단계 | 멀티홉 반복 정제 |
| **워크플로** | 고정 시퀀스 | 자율적 태스크 오케스트레이션 |
| **확장성** | 데이터셋 제한 | 멀티 에이전트 병렬 처리 |

### 2.2 핵심 아키텍처 패턴 5가지

#### 패턴 1: Single-Agent Router (권장 시작점)

```
사용자 쿼리
    │
    ▼
[라우팅 에이전트] ──── 쿼리 분석 & 의도 파악
    │
    ├── 벡터 검색 (유사도 기반)
    ├── SQL/구조화 쿼리 (정확한 수치)
    ├── 웹 검색 (최신 정보)
    └── API 호출 (외부 서비스)
    │
    ▼
[응답 생성] ← 검색 결과 종합
```

- 단일 에이전트가 모든 라우팅/검색/생성 담당
- **단순하고 유지보수 쉬움**, 소규모 프로젝트에 적합
- 우리 프로젝트의 1단계로 적합

#### 패턴 2: Multi-Agent 시스템

```
[코디네이터 에이전트]
    ├── [Excel 전문 에이전트] → 판매/마케팅 데이터
    ├── [PDF 전문 에이전트] → 문서 검색
    ├── [이미지 전문 에이전트] → 상품사진/영수증
    └── [요약 에이전트] → 결과 종합
```

- 각 에이전트가 특정 데이터 소스/유형에 최적화
- **확장성 우수**, 복잡한 멀티스텝 태스크에 적합
- 우리 프로젝트의 2-3단계 목표

#### 패턴 3: 계층적(Hierarchical) 아키텍처

- 상위 에이전트가 전략 수립, 하위 에이전트가 실행
- 쿼리 복잡도와 소스 신뢰도 기반 우선순위 결정

#### 패턴 4: 그래프 기반 프레임워크

- 지식 그래프 + 비구조화 문서 결합
- 멀티홉 추론에 강점 (Agent-G, GeAR)

#### 패턴 5: Agentic Document Workflows (ADW)

- 문서 파싱 → 검색 → 추론 → 구조화 출력의 E2E 자동화
- 비즈니스 로직 통합

### 2.3 4대 에이전트 설계 패턴

| 패턴 | 설명 | 적용 사례 |
|------|------|-----------|
| **Reflection** | 자기 피드백으로 출력 반복 정제 | 검색 결과 품질 자체 평가 → 재검색 |
| **Planning** | 복잡한 태스크를 서브태스크로 분해 | "매출 추이 분석해줘" → 데이터 추출 → 계산 → 시각화 |
| **Tool Use** | 외부 도구/API 호출로 능력 확장 | 벡터 DB, SQL, 계산기, 웹 검색 |
| **Multi-Agent** | 전문화된 에이전트 간 협업 | Excel 에이전트 + PDF 에이전트 협력 |

### 2.4 워크플로 오케스트레이션 패턴

1. **Prompt Chaining**: 순차 태스크 분해 (정확도 높지만 지연 발생)
2. **Routing**: 쿼리 유형별 전문 프로세스로 분기
3. **Parallelization**: 독립 작업 동시 수행으로 지연 감소
4. **Orchestrator-Workers**: 중앙 코디네이터가 동적으로 워커에 태스크 할당
5. **Evaluator-Optimizer**: 평가 모델이 피드백 → 지속적 출력 개선

### 2.5 출처

- [Agentic RAG Survey - arXiv 2501.09136](https://arxiv.org/abs/2501.09136)
- [Agentic RAG Architecture Patterns That Actually Work - DEDICATTED](https://dedicatted.com/insights/agentic-rag-architecture-patterns-that-actually-work-for-enterprise-ai)
- [Building Hierarchical Agentic RAG Systems - InfoQ](https://www.infoq.com/articles/building-hierarchical-agentic-rag-systems/)
- [Top 7 Agentic RAG Architectures - Analytics Vidhya](https://www.analyticsvidhya.com/blog/2025/01/agentic-rag-system-architectures/)
- [5 Most Popular Agentic AI Design Patterns 2025 - Azilen](https://www.azilen.com/blog/agentic-ai-design-patterns/)

### 2.6 우리 프로젝트 적용 시사점

- **1단계**: Single-Agent Router로 시작 → Claude Code가 쿼리 의도를 파악하여 적절한 도구(벡터 검색, SQL 쿼리 등) 선택
- **2단계**: Reflection 패턴 추가 → 검색 결과가 불충분하면 자동으로 재검색/쿼리 재구성
- **3단계**: Multi-Agent로 확장 → 파일 타입별 전문 에이전트 분리
- Claude Code의 MCP 도구 시스템이 **Tool Use 패턴의 자연스러운 구현체**

---

## 3. 로컬/NAS 파일 시스템 RAG 스택

### 3.1 벡터 데이터베이스 비교

| 항목 | ChromaDB | LanceDB | Qdrant | FAISS |
|------|----------|---------|--------|-------|
| **타입** | 클라이언트-서버 | 임베디드 (서버리스) | 클라이언트-서버 | 라이브러리 |
| **언어** | Python | Rust+Python | Rust | C++/Python |
| **설정 난이도** | 매우 쉬움 | 매우 쉬움 | 보통 (Docker) | 보통 |
| **메모리 사용** | ~120MB (idle) | 매우 적음 | ~80MB (idle) | 가변 |
| **적정 규모** | ~수백만 벡터 | 수백만+ 벡터 | 수백만+ 벡터 | 수백만 벡터 |
| **쿼리 지연** | ~20ms | 디스크 기반, 빠름 | ~19ms | 매우 빠름 (인메모리) |
| **메타데이터 필터링** | 기본 | 좋음 | 매우 우수 | 없음 |
| **비용 (1M벡터/월)** | <$30 | <$30 | $30-50 | 무료 |
| **영속성** | 디스크 저장 | 디스크 네이티브 | WAL 기반 | 수동 저장 필요 |
| **하이브리드 검색** | 제한적 | 지원 | 우수 | 미지원 |
| **추천 시나리오** | 빠른 프로토타입, 소규모 | 로컬/임베디드, 대용량 | 복잡한 필터링, 프로덕션 | 연구/벤치마크 |

#### 추천: LanceDB (1순위) 또는 ChromaDB (2순위)

**LanceDB를 1순위로 추천하는 이유:**

1. **서버리스/임베디드**: 별도 서버 프로세스 없이 Python에서 직접 사용. NAS 환경에 최적
2. **디스크 네이티브**: 메모리에 모든 데이터를 올리지 않아도 되므로 Mac Mini 리소스 절약
3. **제로 설정**: `pip install lancedb` 후 로컬 경로만 지정하면 바로 사용
4. **멀티모달 지원**: 이미지 임베딩 저장/검색 네이티브 지원
5. **Lance 포맷**: 컬럼나 포맷으로 대용량 데이터에서도 빠른 접근

```python
# LanceDB 기본 사용 예시
import lancedb

db = lancedb.connect("/Volumes/personal_folder/rag_db")
table = db.create_table("documents", data=[
    {"text": "문서 내용", "vector": [0.1, 0.2, ...], "source": "파일경로", "type": "pdf"}
])
results = table.search([0.1, 0.2, ...]).limit(5).to_list()
```

**ChromaDB를 2순위로 추천하는 이유:**

1. **생태계 성숙도**: 더 많은 튜토리얼, 통합 도구 존재
2. **MCP 서버 지원**: 기존 MCP RAG 서버들이 주로 ChromaDB 사용
3. **빠른 프로토타이핑**: API가 매우 직관적

### 3.2 파일 파싱 도구 비교

| 항목 | Docling (IBM) | LlamaParse | Unstructured |
|------|--------------|------------|--------------|
| **테이블 정확도** | 94%+ (최고) | 좋음 (후처리 필요) | 100% (단순 테이블) |
| **처리 속도** | 보통 | 매우 빠름 (~6초/문서) | 느림 (51초/페이지) |
| **로컬 실행** | 완전 로컬 | 클라우드 API | 로컬 가능 |
| **Excel 지원** | 좋음 (TableFormer) | 좋음 | 좋음 |
| **PDF 지원** | 우수 (DocLayNet) | 우수 | 우수 |
| **이미지/OCR** | 기본 | 우수 (Agentic OCR) | 기본 |
| **비용** | 무료 (오픈소스) | 유료 API | 오픈소스 + 유료 |
| **설치 복잡도** | 보통 | 쉬움 (API) | 복잡함 |

#### 추천: Docling (1순위)

- **완전 로컬 실행**으로 NAS 데이터 프라이버시 보장
- IBM Research 개발, 오픈소스
- TableFormer 모델로 **Excel/PDF 테이블 구조 인식** 우수
- LlamaIndex와 직접 통합 가능

```python
# Docling 사용 예시
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("/Volumes/personal_folder/sales_report.xlsx")
# 테이블 구조가 보존된 상태로 텍스트 추출
```

### 3.3 임베딩 모델 비교

| 모델 | 차원 | 한국어 지원 | 로컬 실행 | 비용 | 품질 |
|------|------|-----------|----------|------|------|
| **OpenAI text-embedding-3-small** | 1536 | 좋음 | X (API) | 유료 | 높음 |
| **OpenAI text-embedding-3-large** | 3072 | 좋음 | X (API) | 유료 | 매우 높음 |
| **Cohere embed-multilingual-v3** | 1024 | 우수 | X (API) | 유료 | 높음 |
| **BGE-M3** | 1024 | 좋음 | O | 무료 | 높음 |
| **BGE-m3-ko (한국어 파인튜닝)** | 1024 | 매우 우수 | O | 무료 | 한국어 최적 |
| **paraphrase-multilingual-MiniLM** | 384 | 보통 | O | 무료 | 보통 |
| **all-MiniLM-L6-v2** | 384 | 제한적 | O | 무료 | 보통 (영어 중심) |

#### 추천: BGE-M3 또는 BGE-m3-ko (한국어 파인튜닝)

**BGE-M3를 추천하는 이유:**

1. **멀티링구얼**: 100개 이상 언어 지원, 한국어 성능 우수
2. **멀티 기능**: Dense + Sparse + ColBERT 검색 모두 지원
3. **긴 문서**: 최대 8192 토큰 처리 가능
4. **완전 로컬**: sentence-transformers로 실행, API 비용 없음
5. **한국어 변종 존재**: `dragonkue/BGE-m3-ko`, `upskyy/bge-m3-korean`

```python
# BGE-M3 사용 예시
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-m3")
# 또는 한국어 최적화 버전
model = SentenceTransformer("upskyy/bge-m3-korean")

embeddings = model.encode(["마케팅 분석 보고서", "2024년 매출 현황"])
```

### 3.4 청킹 전략 (문서 타입별)

| 문서 타입 | 청킹 전략 | 청크 크기 | 오버랩 |
|-----------|----------|----------|--------|
| **PDF (텍스트)** | 시맨틱 청킹 (의미 단위) | 512-1024 토큰 | 50-100 토큰 |
| **PDF (영수증)** | 문서 단위 (1영수증=1청크) | 전체 | 없음 |
| **Excel (분석)** | 시트/테이블 단위 | 행 그룹 (10-20행) | 2-3행 |
| **Excel (수치)** | 컬럼 헤더 + 데이터 행 결합 | 가변 | 헤더 항상 포함 |
| **이미지** | 메타데이터 + 캡션 + OCR | 가변 | 없음 |
| **회사소개서** | 섹션 기반 (제목 기준 분할) | 512-1024 토큰 | 100 토큰 |

**핵심 원칙:**
- 테이블은 절대 행 단위로 자르지 말 것 → 컬럼 헤더가 소실됨
- 각 청크에 **메타데이터 반드시 첨부**: 파일경로, 시트명, 페이지번호, 생성일
- 숫자 데이터는 벡터 검색만으로 부족 → **하이브리드 검색(벡터 + SQL/키워드)** 필수

### 3.5 출처

- [Vector Database Comparison 2026 - 4xxi](https://4xxi.com/articles/vector-database-comparison/)
- [Best Vector Databases 2026 - DataCamp](https://www.datacamp.com/blog/the-top-5-vector-databases)
- [LanceDB Documentation](https://docs.lancedb.com/quickstart)
- [PDF Table Extraction Showdown: Docling vs LlamaParse vs Unstructured](https://boringbot.substack.com/p/pdf-table-extraction-showdown-docling)
- [Docling vs LlamaParse vs Unstructured - Reducto](https://llms.reducto.ai/document-parser-comparison)
- [BGE-M3 - Hugging Face](https://huggingface.co/BAAI/bge-m3)
- [BGE-m3-korean - Hugging Face](https://huggingface.co/upskyy/bge-m3-korean)

---

## 4. Claude Code/MCP 통합 패턴

### 4.1 MCP 기반 RAG 아키텍처

MCP(Model Context Protocol)는 Anthropic이 개발한 오픈 표준으로, AI 어시스턴트가 외부 도구/데이터소스와 상호작용하는 표준화된 방법을 제공합니다.

```
Claude Code
    │
    ▼
[MCP 프로토콜] ──── stdio 또는 SSE 전송
    │
    ▼
[RAG MCP 서버] ──── 7-9개 도구 노출
    │
    ├── index_document (문서 인덱싱)
    ├── rag_query (시맨틱 검색)
    ├── rag_search (키워드 + 벡터 검색)
    ├── get_stats (통계 조회)
    ├── list_files (인덱싱된 파일 목록)
    └── delete_by_source (소스 삭제)
    │
    ▼
[벡터 DB] + [임베딩 모델]
```

### 4.2 기존 MCP RAG 서버 옵션

#### 옵션 1: claude-code-helper (가장 포괄적)

- **저장소**: [michelabboud/claude-code-helper](https://github.com/michelabboud/claude-code-helper)
- **백엔드 선택지**: Redis (4ms 지연), Qdrant, ChromaDB
- **임베딩**: 로컬 (all-MiniLM-L6-v2) 또는 OpenAI
- **기능**: `/rag index`, `/rag search`, `/rag similar` 등 슬래시 커맨드
- **장점**: 10단계 설정 마법사, 멀티 프로젝트/컬렉션 지원, 자동 발견(CLAUDE.md)
- **설정**:

```json
// ~/.claude/mcp.json
{
  "mcpServers": {
    "rag": {
      "command": "node",
      "args": ["/path/to/mcp-servers/rag-mcp/dist/index.js"],
      "env": {
        "RAG_BACKEND": "chromadb",
        "RAG_HOST": "localhost",
        "RAG_PORT": "8000"
      }
    }
  }
}
```

#### 옵션 2: mcp-local-rag (프라이버시 우선)

- **저장소**: [shinpr/mcp-local-rag](https://github.com/shinpr/mcp-local-rag)
- **벡터 DB**: LanceDB (서버리스)
- **임베딩**: Transformers.js (완전 로컬)
- **기능**: 시맨틱 + 키워드 하이브리드 검색, 인접 청크 확장
- **지원 파일**: PDF, DOCX, TXT, Markdown, HTML
- **설치**: `npx` 한 줄 명령 (Docker 불필요)
- **장점**: 완전 오프라인, 외부 API 없음, 무료

```bash
# Claude Code에 추가
claude mcp add local-rag -- npx -y mcp-local-rag --base-dir /Volumes/personal_folder
```

#### 옵션 3: mcp-rag-server (하이브리드 검색)

- **저장소**: [0xrdan/mcp-rag-server](https://github.com/0xrdan/mcp-rag-server)
- **벡터 DB**: ChromaDB
- **임베딩**: OpenAI text-embedding-3-large
- **기능**: 하이브리드 검색, 쿼리 확장, 시맨틱 청킹
- **도구**: rag_query, rag_search, index_document, index_documents_batch 등 7개

#### 옵션 4: Qdrant RAG MCP Server

- **저장소**: [mcpservers.org/servers/ancoleman/qdrant-rag-mcp](https://mcpservers.org/servers/ancoleman/qdrant-rag-mcp)
- **벡터 DB**: Qdrant
- **장점**: 고급 필터링, 대규모 데이터셋

### 4.3 커스텀 MCP RAG 서버 구축 (추천)

기존 솔루션들이 우리 요구사항(Excel, 이미지, 한국어, NAS 통합)을 완벽하게 충족하지 못하므로, 커스텀 서버 구축을 권장합니다.

```
커스텀 MCP RAG 서버 아키텍처
==========================

[Claude Code]
     │ (MCP stdio)
     ▼
[NAS RAG MCP 서버] (Python/Node.js)
     │
     ├── [파일 감시] ← NAS 동기화 디렉토리 모니터링
     │     └── watchdog / fsnotify
     │
     ├── [파싱 엔진]
     │     ├── Docling (PDF, Excel 테이블)
     │     ├── OCR (Tesseract/EasyOCR) → 영수증/이미지
     │     └── 메타데이터 추출기
     │
     ├── [임베딩 엔진]
     │     ├── BGE-M3 (텍스트 → 벡터)
     │     └── CLIP (이미지 → 벡터) [선택사항]
     │
     ├── [벡터 DB]
     │     └── LanceDB (로컬 임베디드)
     │          └── 저장 경로: /Volumes/personal_folder/rag_db
     │
     └── [도구 인터페이스]
           ├── search_documents (시맨틱 검색)
           ├── search_excel (구조화 쿼리)
           ├── search_receipts (영수증 검색)
           ├── index_file (단일 파일 인덱싱)
           ├── index_directory (디렉토리 인덱싱)
           ├── get_file_info (파일 메타데이터)
           └── list_indexed (인덱싱 현황)
```

### 4.4 Claude Code 통합 설정

```json
// ~/.claude/mcp.json 에 추가
{
  "mcpServers": {
    "nas-rag": {
      "command": "python",
      "args": ["/Users/j_mac_mini/Desktop/Vibe Coding/nas_sync/mcp_rag_server/server.py"],
      "env": {
        "NAS_PATH": "/Volumes/personal_folder",
        "RAG_DB_PATH": "/Volumes/personal_folder/rag_db",
        "EMBEDDING_MODEL": "BAAI/bge-m3"
      }
    }
  }
}
```

### 4.5 출처

- [Claude Code MCP 연결 공식 문서](https://code.claude.com/docs/en/mcp)
- [claude-code-helper RAG MCP Guide](https://github.com/michelabboud/claude-code-helper/blob/main/guides/RAG-MCP-GUIDE.md)
- [mcp-local-rag - GitHub](https://github.com/shinpr/mcp-local-rag)
- [mcp-rag-server - GitHub](https://github.com/0xrdan/mcp-rag-server)
- [Qdrant RAG MCP Server](https://mcpservers.org/servers/ancoleman/qdrant-rag-mcp)
- [MCP 공식 사이트](https://modelcontextprotocol.io/docs/develop/connect-local-servers)

### 4.6 우리 프로젝트 적용 시사점

- **빠른 시작**: `mcp-local-rag`를 설치하여 NAS 디렉토리를 바로 인덱싱 (LanceDB 기반, Docker 불필요)
- **중기 목표**: 커스텀 MCP 서버 구축 (Excel 테이블 인식, 한국어 임베딩, 이미지 OCR)
- **CLAUDE.md에 RAG 가용성 힌트 추가**: Claude Code가 세션 시작 시 RAG 도구를 인식하도록 설정
- NAS 경로(`/Volumes/personal_folder`)를 MCP 서버의 `BASE_DIR`로 설정

---

## 5. 비정형 데이터(Excel, 이미지, 한국어) RAG

### 5.1 Excel 파일 RAG 모범 사례

#### 핵심 원칙

1. **테이블 구조 보존이 최우선**: 일반 텍스트 청킹은 테이블 관계를 파괴함
2. **테이블 인식 청킹**: 행-열 관계를 유지하며 분할 → 검색 실패율 35% 감소
3. **시맨틱 임베딩**: 셀 간 관계를 이해하는 의미 기반 벡터화
4. **하이브리드 검색 필수**: 벡터 검색(의미) + 결정론적 쿼리(정확한 수치)

#### 실전 구현 전략

```
Excel 파일 처리 파이프라인
=========================

[Excel 파일]
     │
     ▼
[Docling/pandas] ── 시트별 파싱
     │
     ├── 메타데이터 추출
     │     ├── 파일명, 시트명
     │     ├── 컬럼 헤더
     │     ├── 날짜 범위
     │     └── 데이터 타입
     │
     ├── 테이블 청킹
     │     ├── 헤더 행 + 데이터 행 그룹 (10-20행)
     │     ├── 요약 통계 별도 청크
     │     └── 차트/피벗 테이블 텍스트 변환
     │
     └── 듀얼 인덱싱
           ├── 벡터 인덱스 (시맨틱 검색용)
           └── 구조화 인덱스 (정확한 수치 검색용, SQLite/DuckDB)
```

#### 마케팅/판매 분석 Excel 특화 전략

```python
# Excel 청킹 예시
import pandas as pd

def chunk_excel_for_rag(file_path):
    chunks = []
    xls = pd.ExcelFile(file_path)

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name)

        # 1. 시트 요약 청크
        summary = f"시트: {sheet_name}\n컬럼: {', '.join(df.columns)}\n"
        summary += f"행 수: {len(df)}\n"
        for col in df.select_dtypes(include='number').columns:
            summary += f"{col} 합계: {df[col].sum()}, 평균: {df[col].mean():.2f}\n"
        chunks.append({
            "text": summary,
            "metadata": {"file": file_path, "sheet": sheet_name, "type": "summary"}
        })

        # 2. 데이터 행 그룹 청크 (헤더 항상 포함)
        header = " | ".join(df.columns)
        for i in range(0, len(df), 15):
            group = df.iloc[i:i+15]
            text = f"시트: {sheet_name}\n헤더: {header}\n"
            text += group.to_string(index=False)
            chunks.append({
                "text": text,
                "metadata": {
                    "file": file_path, "sheet": sheet_name,
                    "type": "data", "rows": f"{i}-{i+len(group)}"
                }
            })

    return chunks
```

### 5.2 이미지 RAG (상품사진, 영수증)

#### 두 가지 접근법

**접근법 A: 모달리티 변환 (권장 시작점)**
- 이미지 → OCR + 캡션 → 텍스트로 변환 → 일반 텍스트 RAG
- 장점: 기존 텍스트 RAG 인프라 재사용, 구현 간단
- 단점: 시각적 레이아웃/색상 정보 일부 소실

```
[이미지 파일]
     │
     ├── [OCR 엔진] → 텍스트 추출 (영수증의 금액, 날짜 등)
     │     └── Tesseract (한국어 지원) 또는 EasyOCR
     │
     ├── [VLM 캡션] → 이미지 설명 생성 (상품 특성 등)
     │     └── Claude Vision API 또는 LLaVA
     │
     └── [메타데이터]
           ├── EXIF 데이터 (촬영일, 카메라)
           ├── 파일명, 폴더 경로
           └── 사용자 태그 (있는 경우)
     │
     ▼
[텍스트 임베딩] → 벡터 DB 저장
```

**접근법 B: 네이티브 멀티모달 (장기 목표)**
- CLIP 등 멀티모달 임베더로 이미지 직접 벡터화
- 장점: 시각 정보 완전 보존, 이미지-텍스트 교차 검색
- 단점: 구현 복잡, 아직 성숙한 프로덕션 솔루션 부족 (2025 기준)

#### 상품사진 메타데이터 활용

```python
# 상품사진 메타데이터 추출 및 인덱싱 예시
def process_product_image(image_path):
    metadata = {
        "file_path": image_path,
        "file_name": os.path.basename(image_path),
        "folder": os.path.dirname(image_path),  # 폴더명 = 카테고리 힌트
        "created": os.path.getctime(image_path),
    }

    # EXIF 데이터 추출
    from PIL import Image
    img = Image.open(image_path)
    exif = img._getexif() or {}
    metadata["resolution"] = f"{img.width}x{img.height}"

    # OCR (영수증인 경우)
    if "receipt" in image_path.lower() or "영수증" in image_path:
        import easyocr
        reader = easyocr.Reader(['ko', 'en'])
        ocr_text = reader.readtext(image_path, detail=0)
        metadata["ocr_text"] = " ".join(ocr_text)

    # 폴더 구조에서 카테고리 추론
    # /Volumes/personal_folder/상품사진/전자제품/... → 카테고리: 전자제품
    parts = image_path.split("/")
    if "상품사진" in parts:
        idx = parts.index("상품사진")
        if idx + 1 < len(parts) - 1:
            metadata["category"] = parts[idx + 1]

    return metadata
```

#### 영수증 특화 처리

```python
def process_receipt(image_path):
    """영수증 이미지를 구조화된 데이터로 변환"""
    import easyocr

    reader = easyocr.Reader(['ko', 'en'])
    results = reader.readtext(image_path, detail=1)

    # OCR 결과를 하나의 텍스트로
    full_text = " ".join([r[1] for r in results])

    # 구조화 (LLM 활용 가능)
    receipt_data = {
        "raw_ocr": full_text,
        "file_path": image_path,
        "type": "receipt",
        # LLM에 요청하여 추출:
        # "date", "total", "store_name", "items" 등
    }

    return receipt_data
```

### 5.3 한국어 문서 RAG 처리 주의점

#### 임베딩 모델 선택

| 모델 | 한국어 성능 | 특징 | 추천 용도 |
|------|-----------|------|-----------|
| **BGE-m3-ko** | 최우수 | 한국어 데이터로 추가 학습 | 한국어 전용 시스템 |
| **upskyy/bge-m3-korean** | 우수 | 1024차원, 한국어 파인튜닝 | 한국어 위주 + 영어 혼재 |
| **BAAI/bge-m3** | 좋음 | 100+ 언어, 8192 토큰 | 다국어 혼재 환경 |
| **Cohere embed-multilingual-v3** | 좋음 | API 기반, 교차언어 검색 | 교차 언어 검색 필요 시 |

#### 한국어 청킹 시 주의사항

1. **형태소 분석 고려**: 한국어는 교착어로 "마케팅분석"을 "마케팅" + "분석"으로 분리해야 검색 정확도 향상
2. **조사/어미 처리**: "매출이", "매출을", "매출의"가 모두 "매출"을 가리킴 → 형태소 분석기(Mecab, Kiwi) 활용
3. **한영 혼용 처리**: 비즈니스 문서에 영어가 섞이므로 멀티링구얼 임베딩 필수
4. **토크나이저 영향**: BPE 기반 토크나이저에서 한국어는 토큰 효율이 낮음 → 청크 크기를 영어 대비 50-70% 수준으로 설정
5. **시맨틱 청킹 주의**: 한국어 문장 경계 인식이 영어보다 어려움 → KSS(Korean Sentence Splitter) 사용 권장

```python
# 한국어 텍스트 전처리 예시
from kiwipiepy import Kiwi

kiwi = Kiwi()

def preprocess_korean(text):
    """한국어 텍스트 전처리: 형태소 분석 + 정규화"""
    # 형태소 분석
    tokens = kiwi.tokenize(text)

    # 핵심 형태소만 추출 (명사, 동사, 형용사)
    key_morphs = [t.form for t in tokens if t.tag.startswith(('NN', 'VV', 'VA'))]

    return {
        "original": text,
        "normalized": " ".join(key_morphs),  # 검색용 정규화 텍스트
    }

# 한국어 문장 분리
import kss
sentences = kss.split_sentences("마케팅 분석 결과를 보고합니다. 2024년 매출은 전년 대비 15% 증가했습니다.")
```

### 5.4 출처

- [Hands-on RAG over Excel Sheets - Daily Dose of DS](https://blog.dailydoseofds.com/p/hands-on-rag-over-excel-sheets)
- [RAG Systems for Financial Tables - Daloopa](https://daloopa.com/blog/analyst-best-practices/rag-systems-for-financial-tables-enhancing-excel-data-with-ai-context)
- [Effective Retrieval Strategies for Spreadsheets - Chitika](https://www.chitika.com/excel-rag-effective-retrieval-strategies/)
- [Guide to Multimodal RAG for Images and Text - KX Systems](https://medium.com/kx-systems/guide-to-multimodal-rag-for-images-and-text-10dab36e3117)
- [Best Practices for Integrating Images into RAG - Milvus](https://milvus.io/ai-quick-reference/what-are-the-best-practices-for-integrating-images-into-rag-systems)
- [BGE-m3-ko - HuggingFace](https://huggingface.co/dragonkue/BGE-m3-ko)
- [bge-m3-korean - HuggingFace](https://huggingface.co/upskyy/bge-m3-korean)

---

## 6. 추천 아키텍처 및 구현 로드맵

### 6.1 최종 추천 스택

```
=== NAS Agentic RAG 추천 스택 ===

파싱 엔진:     Docling (PDF/Excel) + EasyOCR (이미지/영수증)
임베딩 모델:   BGE-M3 또는 BGE-m3-ko (로컬, 무료)
벡터 DB:       LanceDB (임베디드, 서버리스)
보조 DB:       DuckDB 또는 SQLite (Excel 수치 검색용)
MCP 서버:      커스텀 Python 서버
프레임워크:    LlamaIndex (선택사항, 직접 구현도 가능)
한국어 처리:   Kiwi (형태소 분석) + KSS (문장 분리)
```

### 6.2 3단계 구현 로드맵

#### Phase 1: 기본 RAG (1-2주)

**목표**: PDF/텍스트 문서에 대한 기본 시맨틱 검색

```
태스크 목록:
1. LanceDB + BGE-M3 설치 및 기본 구성
2. PDF 파싱 파이프라인 구축 (Docling)
3. 기본 청킹 + 임베딩 + 인덱싱 구현
4. MCP 서버 기본 골격 구축 (search, index 도구)
5. Claude Code에 MCP 서버 연결
6. 회사소개서 PDF로 테스트
```

**핵심 코드 구조:**
```
nas_sync/
├── mcp_rag_server/
│   ├── server.py          # MCP 서버 엔트리포인트
│   ├── indexer.py          # 문서 인덱싱 로직
│   ├── searcher.py         # 검색 로직
│   ├── parsers/
│   │   ├── pdf_parser.py   # PDF 파싱
│   │   ├── excel_parser.py # Excel 파싱
│   │   └── image_parser.py # 이미지/영수증 파싱
│   ├── embeddings.py       # 임베딩 모델 래퍼
│   └── config.py           # 설정
├── rag_db/                 # LanceDB 데이터 (NAS에 저장)
└── tests/
    └── test_rag.py
```

#### Phase 2: 구조화 데이터 통합 (2-3주)

**목표**: Excel 분석 파일 + 하이브리드 검색

```
태스크 목록:
1. Excel 파싱 파이프라인 (Docling + pandas)
2. 테이블 인식 청킹 구현
3. DuckDB/SQLite 구조화 인덱스 추가
4. 하이브리드 검색 (벡터 + SQL) 구현
5. search_excel MCP 도구 추가
6. 마케팅/판매 분석 Excel로 테스트
```

#### Phase 3: Agentic RAG (3-4주)

**목표**: 자율적 검색 전략 선택 + 이미지/영수증 지원

```
태스크 목록:
1. 쿼리 라우팅 에이전트 구현 (문서 검색 vs 수치 검색 vs 이미지 검색)
2. Self-reflection 패턴 추가 (검색 결과 품질 자체 평가)
3. 이미지/영수증 OCR 파이프라인 (EasyOCR)
4. 영수증 구조화 추출 (날짜, 금액, 상호 등)
5. 멀티스텝 검색 패턴 구현
6. NAS 파일 변경 감지 + 자동 재인덱싱 (watchdog)
7. 전체 통합 테스트
```

### 6.3 빠른 시작 대안

커스텀 서버 구축 전에 **즉시 테스트**하고 싶다면:

```bash
# 방법 1: mcp-local-rag로 즉시 시작 (가장 빠름)
claude mcp add local-rag -- npx -y mcp-local-rag --base-dir /Volumes/personal_folder

# 방법 2: claude-code-helper 설정 (더 풍부한 기능)
git clone https://github.com/michelabboud/claude-code-helper.git
cd claude-code-helper/mcp-servers
./install-all.sh
# Claude Code에서: /rag init
```

### 6.4 핵심 의사결정 요약

| 결정 사항 | 추천 | 이유 |
|-----------|------|------|
| 벡터 DB | **LanceDB** | 서버리스, 경량, NAS 경로 직접 사용 가능 |
| 임베딩 모델 | **BGE-M3/BGE-m3-ko** | 한국어 우수, 로컬 실행, 무료, 8192 토큰 |
| 문서 파싱 | **Docling** | 테이블 인식 최고, 로컬, 무료 |
| OCR | **EasyOCR** | 한국어 지원, 설치 간편 |
| MCP 통합 | **커스텀 Python 서버** | NAS 특화 요구사항 충족 |
| 청킹 | **문서 타입별 전략** | Excel은 테이블 단위, PDF는 시맨틱 |
| 검색 | **하이브리드** | 벡터 + 키워드 + SQL (수치) |
| 한국어 | **Kiwi + KSS** | 형태소 분석 + 문장 분리 |

### 6.5 주의사항 및 리스크

1. **Mac Mini 리소스 제약**: BGE-M3 모델은 약 2GB GPU/RAM 필요. Mac Mini M 시리즈는 충분히 감당 가능
2. **NAS 네트워크 지연**: 벡터 DB를 NAS에 저장하면 네트워크 I/O 영향. 벡터 DB는 로컬에, 원본 파일만 NAS에 두는 것도 고려
3. **인덱싱 시간**: 대량 문서 초기 인덱싱에 시간 소요. watchdog으로 증분 인덱싱 구현 필수
4. **한국어 임베딩 품질**: 영어 대비 아직 갭 존재. 검색 결과에 대한 지속적 평가/튜닝 필요
5. **멀티모달 성숙도**: 이미지 RAG는 아직 프로덕션 수준에 미도달 (2025-2026 기준). 텍스트 변환 접근이 현실적

---

## 부록: 핵심 참고 자료

### 종합 가이드
- [Agentic RAG Survey - arXiv](https://arxiv.org/abs/2501.09136)
- [From RAG to Context - RAGFlow 2025 Review](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)

### 벡터 DB
- [Vector Database Comparison 2026 - 4xxi](https://4xxi.com/articles/vector-database-comparison/)
- [LanceDB Documentation](https://docs.lancedb.com/quickstart)
- [LanceDB vectordb-recipes (예제)](https://github.com/lancedb/vectordb-recipes)

### MCP/Claude Code
- [Claude Code MCP 공식 문서](https://code.claude.com/docs/en/mcp)
- [claude-code-helper RAG MCP Guide](https://github.com/michelabboud/claude-code-helper/blob/main/guides/RAG-MCP-GUIDE.md)
- [mcp-local-rag](https://github.com/shinpr/mcp-local-rag)
- [mcp-rag-server](https://github.com/0xrdan/mcp-rag-server)

### 파싱/임베딩
- [Docling vs LlamaParse vs Unstructured](https://boringbot.substack.com/p/pdf-table-extraction-showdown-docling)
- [BGE-M3 - HuggingFace](https://huggingface.co/BAAI/bge-m3)
- [BGE-m3-ko](https://huggingface.co/dragonkue/BGE-m3-ko)
- [bge-m3-korean](https://huggingface.co/upskyy/bge-m3-korean)

### 실전 경험담
- [RAG Best Practices from 100+ Teams - kapa.ai](https://www.kapa.ai/blog/rag-best-practices)
- [Hands-on RAG over Excel Sheets](https://blog.dailydoseofds.com/p/hands-on-rag-over-excel-sheets)
- [Multimodal RAG Guide - KX Systems](https://medium.com/kx-systems/guide-to-multimodal-rag-for-images-and-text-10dab36e3117)

### Agentic RAG
- [Agentic RAG Architecture Patterns - DEDICATTED](https://dedicatted.com/insights/agentic-rag-architecture-patterns-that-actually-work-for-enterprise-ai)
- [Top 7 Agentic RAG Architectures - Analytics Vidhya](https://www.analyticsvidhya.com/blog/2025/01/agentic-rag-system-architectures/)
- [5 Agentic AI Design Patterns - Azilen](https://www.azilen.com/blog/agentic-ai-design-patterns/)
