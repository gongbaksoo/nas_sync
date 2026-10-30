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
  -> 당일 폴더 없음(directory not found)은 정상 처리, 그 외 rclone 실패 시 File Provider cp -p fallback
     (cp 실패로 남은 0바이트 파일은 즉시 삭제)
  -> rclone copy ~/Desktop/sync/ /Volumes/personal_folder/Macmini_backup/ --min-size 1B
     (rclone 없을 때만 rsync --min-size=1 fallback)
  -> rclone check --match 로 NAS에 같은 크기로 있는 파일 목록 생성
  -> 그중 14일 경과 로컬 파일만 삭제
  -> auto_index.py 백그라운드 실행
```

### NAS 전송에 rsync 대신 rclone을 쓰는 이유

- 로컬 sync 폴더의 한글 파일명은 NFC(rclone 복사분)와 NFD(File Provider 복사분)가 섞여 있다.
- NAS(SMB 마운트)는 파일명을 NFD로 돌려주고, NFC 이름으로는 파일 조회도 되지 않는다.
- openrsync(`/usr/bin/rsync`)는 정규화가 다른 이름을 다른 파일로 보고 재전송을 시도하다 `renameat: Resource busy`로 중단된다. `--iconv` 옵션도 없다.
- rclone은 정규화가 다른 이름을 같은 파일로 비교하므로 실제로 필요한 파일만 전송한다.

## 4. 실패 처리

| 실패 | 처리 |
|------|------|
| rclone 미설치 | WARN 로그 후 File Provider fallback |
| launchd PATH에 Homebrew 경로 없음 | 스크립트에서 `/opt/homebrew/bin:/usr/local/bin`을 PATH에 추가하고 절대경로 후보를 직접 확인 |
| `gdrive_nas:` remote 없음 | WARN 로그 후 당일 폴더 File Provider fallback |
| `gdrive_screenshots:` remote 없음 | WARN 로그 후 Screen Shot File Provider fallback |
| 당일 폴더 아직 없음 | `directory not found` 감지 시 OK 로그 후 fallback 없이 진행 |
| rclone copy 실패 | exit code/stderr 3줄 로그 후 File Provider fallback |
| File Provider `cp -p` 실패 | WARN 로그, 0바이트로 남은 대상 파일 삭제 |
| NAS 미마운트 | 기존 SMB 재연결 시도 후 실패 시 종료 |
| NAS 전송 중 일부 파일 실패 | WARN 로그(전송/실패 수, 오류 5줄) 후 계속 진행. 실패 파일은 NAS 확인이 안 되므로 로컬에서 삭제되지 않음 |
| NAS 전송 전체 실패 | ERROR 로그 + Slack 알림 후 종료 (로컬 삭제·인덱싱 생략) |
| 14일 경과했지만 NAS 미확인 | 로컬 보존, `WARN: ... 로컬 보존 (N개)` 로그 |
| rclone 없음 | NAS 전송은 rsync fallback, 14일 로컬 삭제는 생략 |
| RAG 인덱싱 중복 | 기존 실행 감지 시 skip |
| 잠금은 있는데 PID 프로세스 없음 | `WARN: 남은 잠금 해제` 후 잠금을 다시 잡고 진행 (PID 없는 이전 형식 잠금은 10분 경과 시) |
| NAS 전송이 2700초 초과 (SMB 응답 없음, macOS 권한 허용 창 대기) | 종료 후 ERROR 로그 + Slack 알림, 다음 정각에 재시도 (ERR-020) |
| NAS 확인(`rclone check`)이 2700초 초과 | 확인 목록 폐기, 14일 로컬 삭제 생략 |

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

## 7. 2026-10-29 변경 및 운영 검증

- 배경: 당일 폴더가 없을 때 rclone 실패 → File Provider 전체 스캔 → `cp` 실패로 0바이트 파일 생성 → rsync가 NAS 원본을 0바이트로 덮어씀 (ERR-017). 이어서 NAS 전송 rsync가 한글 파일명 정규화 차이로 중단됨 (ERR-018).
- 변경: 3장 흐름과 4장 실패 처리 표의 내용을 운영 스크립트와 repository 사본에 반영했다.
- 복구: Google Drive 원본으로 NAS 0바이트 파일 4,142개 복구, 복구 대상 4,144개 크기 전부 일치.
- 검증:
  - 1차 수동 실행: NAS 전송 13개, 14일 경과 로컬 삭제 11개, exit 0
  - 2차 수동 실행: NAS 전송 0개 (재전송 없음)
  - NAS 0바이트 파일 0개
  - 삭제 로직: 임시 폴더 시험에서 NAS에 같은 크기로 있는 파일만 삭제되고, NAS에 없거나 크기가 다른 파일은 보존됨
- 확인된 사실: Google Drive에는 NAS의 Work Space 파일이 모두 있지만, Screen Shot은 최근 134개만 있고 예전 스크린샷 1,611개는 NAS에만 있다. NAS를 최종 보관소로 본다.

## 8. 2026-10-30 변경: 잠금 자동 해제와 NAS 작업 시간 제한

- 배경: 00:00 실행이 NAS 쪽 `open` 호출에서 8시간 멈췄고, launchd가 01~08시 실행을 모두 건너뜀 (ERR-020). 강제 종료된 실행이 잠금을 남기는 문제도 있었음 (ERR-019).
- `run_limited <초> <명령>`: 명령을 백그라운드로 실행하고 1초마다 확인. 제한을 넘기면 TERM → 10초 후 KILL, 124 반환. macOS에는 `timeout` 명령이 없어 직접 구현.
- `acquire_lock`: `mkdir` 성공 시 `pid` 기록. 실패 시 기록된 PID가 `sync_to_nas` 프로세스인지 `ps`로 확인하고, 아니면 잠금을 지우고 다시 잡음. 종료 시 `rm -rf`로 잠금 삭제.
- Google Drive 쪽 rclone은 네트워크 backend라 자체 `--timeout`(기본 5분)이 있어 감싸지 않음.
- 운영 확인 (2026-10-30 11:00): 09시·10시 실행이 시간 제한으로 종료되어 다음 실행이 막히지 않음을 확인. 원인은 macOS 네트워크 볼륨 허용 창 대기였고, 허용 후 11시 실행에서 NAS 전송 37개, NAS 확인 기반 14일 로컬 삭제 34개(보존 0개)가 처음 실제 동작함.
