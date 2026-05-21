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

## 3. 동작 흐름

```text
launchd
  -> ~/sync_to_nas.sh
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
