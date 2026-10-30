# NAS 동기화 시스템 인수인계 문서

## 1. 환경 정보

| 항목 | 값 |
|------|------|
| 클라이언트 | Mac Mini (Wi-Fi) |
| NAS | UGREEN DXP2800-DBEC (유선) |
| NAS IP | 192.168.0.235 |
| SMB 주소 | smb://192.168.0.235/personal_folder |
| NAS 계정 | gongbaksoo / macOS Keychain 저장 |
| OS | macOS Darwin 25.3.0 |
| 사용자 | j_mac_mini |

## 2. 현재 구성 상태

### 설치 완료된 파일

| 파일 | 경로 | 상태 |
|------|------|------|
| 동기화 스크립트 | ~/sync_to_nas.sh | 설치 완료, 실행 권한 부여됨 |
| launchd plist | ~/Library/LaunchAgents/com.sync.nas.plist | 등록 완료, 활성화됨 |
| 로컬 동기화 폴더 | ~/Desktop/sync/ | 생성 완료 |
| 하위 폴더 | ~/Desktop/sync/문서/, ~/Desktop/sync/상품이미지/ | 생성 완료 (사용 선택사항) |
| 로그 파일 | ~/.sync_nas.log | 자동 생성됨 |
| 운영 인수인계 문서 | docs/03-sop/nas-sync-handoff.md | 생성 완료 |
| RAG Plan 문서 | docs/01-plan/features/nas-agentic-rag.plan.md | 생성 완료 |
| Google Drive Plan 문서 | docs/01-plan/features/gdrive-to-sync.plan.md | 생성 완료 |

### NAS 폴더 구조

```
/Volumes/personal_folder/
├── Macmini_backup/    ← 동기화 대상 폴더 (2026-10-29 기준 약 6,490개)
├── sync_logs/         ← 오래된 동기화 로그 압축 보관
├── rag_db/            ← LanceDB SMB 저장 실패(ERR-001) 당시 잔여물, 현재 미사용
├── PC_AVK_backup/
├── Photos/
├── backup/
└── #recycle/
```

## 3. 동기화 로직 요약

```
~/Desktop/sync/ → /Volumes/personal_folder/Macmini_backup/
```

- 방향: Mac Mini → NAS 단방향
- 스케줄: 매일 07:00~24:00 매시 정각 (18회/일, launchd Hour 0 포함) + 부팅 시 1회
- 대상 확장자: xlsx, xls, xlsb, csv, pptx, ppt, pdf, zip, html, htm, jpg, jpeg, png, gif, webp
- 제외: ~$* (Office 임시파일), .DS_Store, Thumbs.db
- 로컬 보관: 로컬 sync 폴더에 들어온 뒤 14일이 지나고, `rclone check`로 NAS에 같은 크기로 있는 것이 확인된 파일만 삭제. 미확인 파일은 로컬에 남겨 다음 실행에서 재전송 (`WARN: ... 로컬 보존 (N개)`)
- NAS 전송: `rclone copy` 사용. 로컬 한글 파일명(NFC/NFD 혼재)과 NAS(NFD)를 같은 파일로 인식함. rclone이 없을 때만 rsync fallback (권한/디렉토리 시간 보존 제외)
- 0바이트 보호: 0바이트 파일은 NAS로 보내지 않음 (`--min-size 1B`). Google Drive 원본부터 빈 파일이면 NAS에 없는 것이 정상이며, 14일 후에도 로컬에 남음
- RAG 인덱싱은 동기화 후 백그라운드 실행하며 중복 실행은 건너뜀 (`~/.sync_nas_index.log`)
- 중복 동기화 방지를 위해 `~/.sync_nas.lock` 락 디렉토리를 사용하고 안에 실행 PID(`pid`)를 기록함. 다음 실행 때 그 프로세스가 없으면 잠금을 자동 해제함 (`WARN: 남은 잠금 해제`)
- NAS 작업(`rclone copy`, `rclone check`)은 2700초(`NAS_STEP_TIMEOUT`)를 넘기면 종료함. SMB 응답이 끊기거나 macOS 권한 허용 창을 기다려도 다음 정각 실행이 막히지 않게 하기 위함 (ERR-020)
- macOS 네트워크 볼륨 접근 권한이 필요함. 허용 창이 뜨면 정기 실행은 응답을 기다리며 멈추므로 Mac mini 화면에서 허용해야 함 (2026-10-30 재요청 발생)
- Google Drive 당일 Download Backup/YYYY/YYMM/YYMMDD 폴더는 rclone Google Drive API로 우선 복사함
- rclone remote 이름은 `gdrive_nas:`이고, root folder는 Work Space (`15FxOAg39qbr7jLOtEMceEyFXJ34H24TW`)
- Screen Shot은 `gdrive_screenshots:` remote를 사용하고, root folder는 Screen Shot (`1rPE71JlLqAcq1BNZI5kE8mKwo0-2hCpf`)
- launchd 환경에서도 rclone을 찾도록 스크립트 내부에서 `/opt/homebrew/bin`, `/usr/local/bin` PATH와 절대경로 후보를 확인함
- 당일 폴더가 아직 없으면(`directory not found`) 정상으로 처리하고 fallback을 실행하지 않음
- 그 외 rclone 실패 시 Google Drive File Provider 경로에서 `cp -p` fallback 복사. `cp` 실패로 남은 0바이트 파일은 즉시 삭제
- rsync fallback은 `--timeout=300`(운영 스크립트 기준)으로 무한 대기 방지
- NAS 전송 중 일부 파일만 실패하면 전송/실패 수를 WARN 로그에 남기고 계속 진행 (예: `★` 포함 파일명)
- NAS 미연결 시: open smb:// 로 재연결 시도 → 실패 시 로그 기록 후 다음 스케줄 대기
- Slack 알림: 동기화 완료(파일 전송 있을 때), NAS 연결 실패, NAS 전송 실패 시 Slack Incoming Webhook으로 알림 전송
- Slack 웹훅 URL은 운영 스크립트(`~/sync_to_nas.sh`)에만 있고 repository 사본에는 넣지 않음 (Slack 코드 자체가 repository 사본에는 없음)
- Google Drive는 영구 보관소가 아님: MacBook에서 지운 파일은 Google Drive에서도 지워질 수 있고, Screen Shot은 최근 파일만 남음 (2026-10-29: 예전 스크린샷 1,611개는 NAS에만 있음). NAS가 최종 보관소
- 로그 파일: `~/.sync_nas.log`

## 4. 운영 명령어

```bash
# 수동 동기화
~/sync_to_nas.sh

# 로그 확인
tail -20 ~/.sync_nas.log

# rclone remote 확인
rclone lsd gdrive_nas:

# 오늘 Download Backup API 목록 확인
rclone lsf gdrive_nas:"Download Backup/$(date '+%Y')/$(date '+%y%m')/$(date '+%y%m%d')"

# Screen Shot API 목록 확인
rclone lsf gdrive_screenshots:

# 자동 동기화 중지
launchctl unload ~/Library/LaunchAgents/com.sync.nas.plist

# 자동 동기화 재시작
launchctl load ~/Library/LaunchAgents/com.sync.nas.plist

# 스케줄러 등록 상태 확인
launchctl list | grep sync.nas

# NAS 수동 마운트
open 'smb://gongbaksoo@192.168.0.235/personal_folder'

# NAS 마운트 확인
ls /Volumes/personal_folder/

# NAS 0바이트 파일 점검 (0이어야 정상)
find /Volumes/personal_folder/Macmini_backup -type f -size 0 ! -name '.DS_Store' | wc -l

# 정각 로그가 끊겼거나 "NAS 동기화 시간 초과"가 나올 때:
# 1) Mac mini 화면에 "네트워크 볼륨의 파일에 접근" 허용 창이 떠 있는지 확인 → 허용
#    (시스템 설정 → 개인정보 보호 및 보안 → 파일 및 폴더 / 전체 디스크 접근 권한에서 bash·rclone 확인)
# 2) 멈춘 실행이 있는지 확인 (launchd는 실행 중이면 다음 스케줄을 건너뜀)
pgrep -fl "sync_to_nas|rclone|rsync"

# 남은 잠금은 다음 실행 때 자동 해제됨. 수동으로 지울 때는 프로세스가 없는 것을 확인한 뒤
pgrep -f sync_to_nas || rm -rf ~/.sync_nas.lock

# 로그가 커졌을 때 NAS에 압축 보관 후 비우기 (자동 동기화 중지 상태에서)
gzip -c ~/.sync_nas.log > /Volumes/personal_folder/sync_logs/sync_nas_log_until_$(date +%Y%m%d).log.gz && : > ~/.sync_nas.log
```

> 주의: `launchctl unload`는 실행 중인 동기화를 강제 종료하며, 이때 `~/.sync_nas.lock`이 남는다 (ERR-019). 2026-10-30부터는 다음 실행이 PID를 확인해 자동 해제한다.

## 5. 미완료 작업 (다음 AI가 진행해야 할 것)

### 5-1. NAS 폴더 자동 분류 (핵심)

현재 상태: ~/Desktop/sync/ 의 폴더 구조를 그대로 NAS에 복사함
요구사항: 사용자가 sync 폴더에 파일을 아무렇게나 넣어도 NAS에는 자동 분류

설계 방향 (사용자 합의 완료):
- 폴더명은 영문 소문자 (AI 토큰화 최적화)
- 경로 자체가 메타데이터 역할 (예: /documents/excel/2026/05/)
- manifest.jsonl 인덱스 파일 생성 (AI가 파일 검색용으로 사용)
- 사람도 볼 수 있을 정도의 가독성 유지

제안된 NAS 폴더 구조:
```
Macmini_backup/
├── documents/
│   ├── excel/
│   │   └── 2026/
│   │       └── 05/
│   ├── presentation/
│   │   └── 2026/
│   │       └── 05/
│   └── pdf/
│       └── 2026/
│           └── 05/
├── images/
│   └── products/
│       └── 2026/
│           └── 05/
└── _index/
    └── manifest.jsonl   ← AI 검색용 인덱스
```

manifest.jsonl 예시:
```jsonl
{"path":"documents/excel/2026/05/매출보고서.xlsx","type":"excel","date":"2026-05-08","size":24500,"synced_at":"2026-05-08T09:00:00"}
{"path":"images/products/2026/05/신발_A001.jpg","type":"image","date":"2026-05-08","size":182000,"synced_at":"2026-05-08T09:00:00"}
```

구현 필요사항:
- sync_to_nas.sh 스크립트에 확장자 기반 분류 로직 추가
- 날짜(YYYY/MM) 폴더 자동 생성
- manifest.jsonl 자동 업데이트 로직
- 사용자에게 최종 구조 확인 후 적용

### 5-2. 대용량 초기 마이그레이션

사용자 언급: "한번은 별도로 대용량 자료를 동기화 할 건데 당장은 아님"
→ 별도 일회성 작업으로 나중에 진행

### 5-3. macOS 키체인 비밀번호 저장

Finder에서 NAS 연결 시 "키체인에 비밀번호 기억" 체크 필요
→ 재부팅 후 자동 연결을 위해 사용자에게 안내

## 6. 사용자 요구사항 정리

| 요구사항 | 상태 |
|----------|------|
| NAS를 메인 저장소로 사용 | 구현 완료 |
| 07~24시 매시 정각 동기화 | 구현 완료 |
| 14일 후 로컬 파일 자동 삭제 | 구현 완료 (NAS 확인된 파일만 삭제, 2026-10-29) |
| 0바이트 파일로 NAS 원본 덮어쓰기 방지 | 구현 완료 (2026-10-29) |
| 오래된 잠금 자동 해제 | 구현 완료 (PID 확인, 2026-10-30) |
| NAS 응답 없음 시 무한 대기 방지 | 구현 완료 (NAS 작업 2700초 제한, 2026-10-30) |
| macOS 네트워크 볼륨 권한 재요청 대응 | 수동 - 화면 허용 창 확인 (4장 명령어 주석) |
| NAS 미연결 시 재연결 | 구현 완료 |
| 동기화 로그 기록 | 구현 완료 |
| Slack 알림 (완료/실패) | 구현 완료 |
| 데스크탑 sync 폴더에서 작업 | 구현 완료 |
| NAS에서 자동 분류 (RAG 최적화) | 미구현 - 설계 합의 중 |
| AI 검색용 manifest.jsonl | 미구현 - 설계 합의 중 |
| 대용량 초기 마이그레이션 | 미착수 - 추후 진행 |

## 7. 관련 문서

- 문서 색인: `docs/README.md`
- RAG Plan: `docs/01-plan/features/nas-agentic-rag.plan.md`
- RAG Design: `docs/02-design/features/nas-agentic-rag.design.md`
- Google Drive Plan: `docs/01-plan/features/gdrive-to-sync.plan.md`
- rclone Design: `docs/02-design/features/gdrive-rclone-sync.design.md`
- RAG 리서치 레퍼런스: `docs/04-references/agentic-rag-guide.md`
- 장애 이력: `docs/error.md`
- 작업 이력: `docs/history.md`

## 8. PDCA 상태

- Phase: Plan (완료)
- 문서: docs/03-sop/nas-sync-handoff.md
- 다음 단계: /pdca design nas-sync → 자동 분류 로직 설계 확정 후 구현
