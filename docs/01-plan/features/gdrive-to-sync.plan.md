# Feature Plan: Google Drive to Sync 자동 동기화

## Executive Summary

| 관점 | 내용 |
|------|------|
| Problem | 맥북에서 Google Drive로 동기화되는 파일이 Mac Mini의 NAS 백업 파이프라인에 자동 연결되지 않음 |
| Solution | 기존 sync_to_nas.sh에 Google Drive API(rclone) → sync 폴더 복사 단계, File Provider fallback, timeout/lock 안전장치 추가 |
| UX Effect | 맥북에서 파일 저장 → 자동으로 NAS까지 백업 완료 (사용자 개입 불필요) |
| Core Value | 맥북 작업 파일의 자동 NAS 백업과 RAG 인덱싱 연결로 데이터 안전성 및 검색 가능성 확보 |

## 1. 핵심 문제

맥북의 Google Drive '내 Mac' 폴더가 Mac Mini에도 동기화되지만, NAS 백업 파이프라인(~/Desktop/sync/ → NAS)과 연결되어 있지 않아 수동 복사가 필요함.

## 2. 대상 사용자

- Mac Mini 관리자 (j_mac_mini)
- 맥북에서 작업하고 Google Drive로 동기화하는 사용자

## 3. 성공 기준

- Google Drive '내 Mac' 하위 파일이 자동으로 ~/Desktop/sync/에 복사됨
- 기존 NAS 동기화 파이프라인과 자연스럽게 연계됨
- Google Drive File Provider가 큰 트리 스캔에서 일부 날짜 폴더를 누락해도 당일 폴더는 rclone으로 우선 보강됨
- 동기화 후 변경 파일 RAG 인덱싱이 백그라운드로 실행되고 중복 실행은 방지됨
- 기존 동기화 기능에 영향 없음

## 4. 탐색한 대안

| 접근 | 설명 | 선택 |
|------|------|------|
| A: 기존 스크립트 확장 | sync_to_nas.sh에 0단계 추가 | 선택 |
| B: 별도 스크립트 | gdrive_to_sync.sh + 별도 launchd | 미선택 |
| C: rsync over SSH | 맥북에서 Mac Mini로 직접 전송 | 불필요 (Google Drive가 이미 동기화) |
| D: rclone + Google Drive API | File Provider를 우회하여 당일 폴더를 API 기반 복사 | 선택 (v2) |

## 5. 아키텍처

### 데이터 흐름
```
맥북 파일 저장
  → Google Drive 클라우드 동기화 (자동)
  → [v2] rclone Google Drive API로 Mac Mini sync 폴더 복사
  → [fallback] Google Drive File Provider 로컬 경로에서 cp -p 복사
  → NAS 동기화 (sync_to_nas.sh 기존 로직)
```

### 소스/목적지 매핑
| 소스 | 목적지 |
|------|--------|
| gdrive_nas:Download Backup/YYYY/YYMM/YYMMDD/ | ~/Desktop/sync/Download Backup/YYYY/YYMM/YYMMDD/ |
| ~/Library/CloudStorage/.../Work Space/Download Backup/YYYY/YYMM/YYMMDD/ | ~/Desktop/sync/Download Backup/YYYY/YYMM/YYMMDD/ (fallback) |
| gdrive_screenshots: | ~/Desktop/sync/Screen Shot/ |
| ~/Library/CloudStorage/.../Screen Shot/ | ~/Desktop/sync/Screen Shot/ (fallback) |

### 확장자 필터
기존 sync_to_nas.sh와 동일: xlsx, xls, xlsb, csv, pptx, ppt, pdf, zip, html, htm, jpg, jpeg, png, gif, webp

### 운영 안전장치

| 항목 | 내용 |
|------|------|
| 중복 실행 방지 | `~/.sync_nas.lock` 락 디렉토리 생성 실패 시 해당 실행은 skip |
| Google Drive API 복사 | `rclone copy gdrive_nas:"Download Backup/YYYY/YYMM/YYMMDD"` 우선 실행 |
| Screen Shot API 복사 | `rclone copy gdrive_screenshots:` 우선 실행 |
| rclone fallback | rclone 미설치/remote 미설정/복사 실패 시 File Provider `cp -p` fallback |
| NAS rsync timeout | `--timeout=60`으로 SMB hang 방지 |
| 당일 폴더 우선 복사 | `Download Backup/YYYY/YYMM/YYMMDD`를 API 기반으로 먼저 복사 |
| 오류 기록 | rclone exit code/stderr 요약 및 fallback 실행 여부를 WARN 로그로 기록 |
| 인덱싱 | 동기화 완료 후 `auto_index.py`를 백그라운드 실행, 이미 실행 중이면 skip |

## 6. YAGNI Review

### MVP 포함
- Work Space 폴더 동기화
- Screen Shot 폴더 동기화
- 확장자 필터링 (xlsx, xls, xlsb, csv, pptx, ppt, pdf, zip, html, htm, jpg, jpeg, png, gif, webp)
- 당일 Download Backup 폴더 rclone 우선 보강
- timeout/lock 기반 운영 안전장치

### 제외 (Out of Scope)
- 전체 파일 동기화 (확장자 제한 없는 모드)
- 양방향 동기화
- 실시간 감시 (fswatch 등)
- 알림 시스템

## 7. 구현 범위

### 변경 파일
- `~/sync_to_nas.sh` — 0단계 (Google Drive → sync) rsync 로직 추가

### 변경 없는 파일
- `~/Library/LaunchAgents/com.sync.nas.plist` — 기존 스케줄 그대로 사용
- NAS 동기화 로직 — 기존 1~3단계 변경 없음

## 8. 리스크

| 리스크 | 대응 |
|--------|------|
| Google Drive 로컬 동기화 지연 | rsync가 현재 상태 기준으로 복사하므로 영향 없음 |
| 경로에 한글/공백 포함 | 변수를 쌍따옴표로 감싸서 처리 |
| Screen Shot 폴더 용량 과다 | 기존 14일 삭제 정책이 sync 폴더에도 적용됨 |
| Google Drive File Provider가 특정 큰 파일에서 mmap 오류 | 당일 폴더를 rclone API 복사로 우선 처리하고 File Provider는 fallback으로만 사용 |
| 이전 실행이 장시간 점유 | lock으로 중복 실행을 skip하고 rsync timeout으로 hang 완화 |
| rclone OAuth/remote 설정 누락 | WARN 로그를 남기고 기존 File Provider fallback으로 동작 |

## 9. 구현 결과

- **구현일**: 2026-05-12
- **상태**: 완료
- **변경 파일**: `~/sync_to_nas.sh`
- **테스트**: dry-run 805개 파일 대상 확인, 실제 실행 성공 (exit code 0)
- **에러 수정**: ERR-004 bash 산술 오류 (grep -c 출력 개행 문제)
- **참고**: Full Disk Access 권한 필요 (rsync가 Google Drive/sync 폴더 접근)
- **Screen Shot 동기화**: 234개 png 파일 정상 복사 확인 (ERR-004로 인해 초기 실행 시 누락, 수정 후 정상)
- **NAS 동기화 완료**: Full Disk Access에 `/bin/bash` 추가 후 launchd 자동 실행 정상 동작 확인. Screen Shot 234개, Work Space 전체 NAS 도착 확인.
- **ERR-006 수정 (2026-05-14)**: rsync `-av` → `-avi` 변경. `-av`에서는 `grep "^>"` 카운트가 항상 0이었음 (전송은 정상이었으나 로그만 부정확)
- **ERR-007 수정 (2026-05-14)**: rsync 필터 순서 변경. `--exclude='~$*'`를 `--include` 앞으로 이동하여 Office 임시 파일 제외 정상 동작
- **확장자 추가 (2026-05-15)**: `.xlsb`, `.zip` 확장자 누락으로 11시 이후 파일 미동기화 → 필터 및 14일 삭제 대상에 추가. 88개 파일 NAS 전송 확인.
- **5/19 보강 (2026-05-20 01:02 KST)**: File Provider 큰 트리 스캔 누락으로 5/19 `260519` 폴더가 로컬/NAS에 비어 있던 문제 확인. 수동 보강 후 로컬/NAS 각 15개 파일 확인, NAS dry-run 0.
- **5/20 보강 (2026-05-20 15:27 KST)**: 5/19 큰 `.xlsb`에서 `mmap: Resource deadlock avoided`가 반복되고 오늘 `260520` 폴더가 로컬/NAS에 누락됨. 당일 폴더 우선 복사, `--timeout=60`, lock, 경고 로깅 추가. 로컬/NAS 각 2개 파일 확인, NAS dry-run 0.
- **RAG 인덱싱 개선 (2026-05-20)**: 동기화 후 인덱싱을 백그라운드로 전환. 파일별 성공/실패 마커 즉시 저장, 임베딩/VectorStore 배치 처리와 진행 로그 추가. 5/20 변경분 45개 인덱싱 성공, 실패 0.
- **rclone 전환 (2026-05-21)**: Work Space 폴더 ID(`15FxOAg39qbr7jLOtEMceEyFXJ34H24TW`)를 root로 하는 `gdrive_nas` remote와 Screen Shot 폴더 ID(`1rPE71JlLqAcq1BNZI5kE8mKwo0-2hCpf`)를 root로 하는 `gdrive_screenshots` remote를 도입. 당일 `Download Backup/YYYY/YYMM/YYMMDD`와 Screen Shot은 rclone API 복사를 우선 사용하고, 실패 시 File Provider `cp -p` fallback을 사용.
