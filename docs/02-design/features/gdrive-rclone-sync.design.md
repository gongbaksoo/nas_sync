# Google Drive rclone Sync Design

> 생성일: 2026-05-21
> Phase: Design
> Plan: `docs/01-plan/features/gdrive-to-sync.plan.md`

## 1. 목표

Google Drive Desktop/File Provider 경로를 직접 읽을 때 발생하는 `mmap: Resource deadlock avoided` 문제를 피하기 위해, 당일 `Download Backup` 폴더는 rclone Google Drive API로 우선 복사한다. NAS 전송, 로컬 보관, RAG 인덱싱은 기존 파이프라인을 유지한다.

## 2. 구성

| 항목 | 값 |
|------|-----|
| Work Space rclone remote | `gdrive_nas:` |
| Screen Shot rclone remote | `gdrive_screenshots:` |
| backend | Google Drive |
| scope | `drive.readonly` |
| Work Space root folder id | `15FxOAg39qbr7jLOtEMceEyFXJ34H24TW` |
| Screen Shot root folder id | `1rPE71JlLqAcq1BNZI5kE8mKwo0-2hCpf` |
| 로컬 대상 | `~/Desktop/sync/Download Backup/YYYY/YYMM/YYMMDD/` |
| NAS 대상 | `/Volumes/personal_folder/Macmini_backup/` |
| rclone binary 탐색 | PATH 보정 후 `command -v rclone`, `/opt/homebrew/bin/rclone`, `/usr/local/bin/rclone` 순서 |

## 3. 동작 흐름

```text
launchd
  -> ~/sync_to_nas.sh
  -> PATH 보정 및 rclone binary 탐색
  -> rclone copy gdrive_nas:Download Backup/YYYY/YYMM/YYMMDD ~/Desktop/sync/Download Backup/YYYY/YYMM/YYMMDD
  -> rclone copy gdrive_screenshots: ~/Desktop/sync/Screen Shot
  -> rclone 실패 시 File Provider cp -p fallback
  -> rsync ~/Desktop/sync/ /Volumes/personal_folder/Macmini_backup/
  -> 14일 경과 로컬 파일 삭제
  -> auto_index.py 백그라운드 실행
```

## 4. 실패 처리

| 실패 | 처리 |
|------|------|
| rclone 미설치 | WARN 로그 후 File Provider fallback |
| launchd PATH에 Homebrew 경로 없음 | 스크립트에서 `/opt/homebrew/bin:/usr/local/bin`을 PATH에 추가하고 절대경로 후보를 직접 확인 |
| `gdrive_nas:` remote 없음 | WARN 로그 후 당일 폴더 File Provider fallback |
| `gdrive_screenshots:` remote 없음 | WARN 로그 후 Screen Shot File Provider fallback |
| rclone copy 실패 | exit code/stderr 3줄 로그 후 File Provider fallback |
| NAS 미마운트 | 기존 SMB 재연결 시도 후 실패 시 종료 |
| RAG 인덱싱 중복 | 기존 실행 감지 시 skip |

## 5. 검증 기준

- `rclone lsf gdrive_nas:"Download Backup/YYYY/YYMM/YYMMDD"`가 오늘 파일을 반환해야 한다.
- `rclone lsf gdrive_screenshots:`가 Screen Shot 파일을 반환해야 한다.
- `~/sync_to_nas.sh` 실행 후 Google Drive/로컬/NAS 오늘 폴더 파일 수가 일치해야 한다.
- NAS dry-run 결과가 `0`이어야 한다.
- `auto_index.py` 재실행 시 `변경된 파일 없음 — 인덱싱 건너뜀`이 나와야 한다.

## 6. 2026-05-22 운영 검증

- 07~09시 정기 실행은 launchd PATH 문제로 `rclone 미설치`가 기록되고 File Provider fallback으로 동작했다.
- 운영 스크립트와 repository 사본에 PATH 보정 및 절대경로 rclone 탐색을 추가했다.
- 수동 실행으로 `260522` 당일 폴더 local/NAS 각 23개 일치, NAS dry-run 0을 확인했다.
- 10시 정기 실행: 당일 폴더 0개 증가, Screen Shot 6개 증가, NAS 전송 6개, RAG 인덱싱 시작.
- 11시 정기 실행: 당일 폴더 0개 증가, Screen Shot 0개 증가, NAS 전송 0개, RAG 인덱싱 시작.
- 10시/11시 로그에는 `rclone 미설치`와 `Resource deadlock avoided`가 재발하지 않았다.
