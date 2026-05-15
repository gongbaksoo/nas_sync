# Feature Plan: Google Drive to Sync 자동 동기화

## Executive Summary

| 관점 | 내용 |
|------|------|
| Problem | 맥북에서 Google Drive로 동기화되는 파일이 Mac Mini의 NAS 백업 파이프라인에 자동 연결되지 않음 |
| Solution | 기존 sync_to_nas.sh에 Google Drive 로컬 폴더 → sync 폴더 복사 단계 추가 |
| UX Effect | 맥북에서 파일 저장 → 자동으로 NAS까지 백업 완료 (사용자 개입 불필요) |
| Core Value | 맥북 작업 파일의 자동 NAS 백업으로 데이터 안전성 확보 |

## 1. 핵심 문제

맥북의 Google Drive '내 Mac' 폴더가 Mac Mini에도 동기화되지만, NAS 백업 파이프라인(~/Desktop/sync/ → NAS)과 연결되어 있지 않아 수동 복사가 필요함.

## 2. 대상 사용자

- Mac Mini 관리자 (j_mac_mini)
- 맥북에서 작업하고 Google Drive로 동기화하는 사용자

## 3. 성공 기준

- Google Drive '내 Mac' 하위 파일이 자동으로 ~/Desktop/sync/에 복사됨
- 기존 NAS 동기화 파이프라인과 자연스럽게 연계됨
- 기존 동기화 기능에 영향 없음

## 4. 탐색한 대안

| 접근 | 설명 | 선택 |
|------|------|------|
| A: 기존 스크립트 확장 | sync_to_nas.sh에 0단계 추가 | 선택 |
| B: 별도 스크립트 | gdrive_to_sync.sh + 별도 launchd | 미선택 |
| C: rsync over SSH | 맥북에서 Mac Mini로 직접 전송 | 불필요 (Google Drive가 이미 동기화) |

## 5. 아키텍처

### 데이터 흐름
```
맥북 파일 저장
  → Google Drive 클라우드 동기화 (자동)
  → Mac Mini Google Drive 로컬 동기화 (자동)
  → [NEW] Mac Mini sync 폴더로 rsync (sync_to_nas.sh 0단계)
  → NAS 동기화 (sync_to_nas.sh 기존 로직)
```

### 소스/목적지 매핑
| 소스 | 목적지 |
|------|--------|
| ~/Library/CloudStorage/GoogleDrive-gongbaksoo@gmail.com/다른 컴퓨터/내 Mac/Work Space/ | ~/Desktop/sync/ |
| ~/Library/CloudStorage/GoogleDrive-gongbaksoo@gmail.com/다른 컴퓨터/내 Mac/Screen Shot/ | ~/Desktop/sync/Screen Shot/ |

### 확장자 필터
기존 sync_to_nas.sh와 동일: xlsx, xls, pptx, ppt, pdf, jpg, jpeg, png, gif, webp

## 6. YAGNI Review

### MVP 포함
- Work Space 폴더 동기화
- Screen Shot 폴더 동기화
- 확장자 필터링 (xlsx, xls, xlsb, pptx, ppt, pdf, zip, jpg, jpeg, png, gif, webp)

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
