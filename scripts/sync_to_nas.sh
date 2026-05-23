#!/bin/bash

# === NAS 동기화 스크립트 ===
# Google Drive → sync → UGREEN NAS (단방향)
# 스케줄: 07:00~24:00 매시 정각 (launchd Hour 0 포함)

SOURCE="$HOME/Desktop/sync/"
NAS_MOUNT="/Volumes/personal_folder/Macmini_backup/"
GDRIVE="$HOME/Library/CloudStorage/GoogleDrive-gongbaksoo@gmail.com/다른 컴퓨터/내 Mac"
LOG="$HOME/.sync_nas.log"
LOCK_DIR="$HOME/.sync_nas.lock"
RCLONE_REMOTE="gdrive_nas:"
RCLONE_SCREENSHOT_REMOTE="gdrive_screenshots:"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

find_rclone() {
    local candidate

    if candidate="$(command -v rclone 2>/dev/null)"; then
        printf '%s\n' "$candidate"
        return 0
    fi

    for candidate in /opt/homebrew/bin/rclone /usr/local/bin/rclone; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    return 1
}

RCLONE_BIN="$(find_rclone || true)"

# rsync 확장자 필터 (공통)
RSYNC_FILTERS=(
    --exclude='~$*' --exclude='.DS_Store' --exclude='Thumbs.db'
    --include='*.xlsx' --include='*.xls' --include='*.xlsb'
    --include='*.csv'
    --include='*.pptx' --include='*.ppt'
    --include='*.pdf' --include='*.zip'
    --include='*.html' --include='*.htm'
    --include='*.jpg' --include='*.jpeg'
    --include='*.png' --include='*.gif' --include='*.webp'
    --include='*/'
    --exclude='*'
)

NAS_RSYNC_OPTS=(-rlti --omit-dir-times --timeout=60)
RCLONE_FILTERS=(
    --filter='- ~$*' --filter='- .DS_Store' --filter='- Thumbs.db'
    --filter='+ *.xlsx' --filter='+ *.xls' --filter='+ *.xlsb'
    --filter='+ *.csv'
    --filter='+ *.pptx' --filter='+ *.ppt'
    --filter='+ *.pdf' --filter='+ *.zip'
    --filter='+ *.html' --filter='+ *.htm'
    --filter='+ *.jpg' --filter='+ *.jpeg'
    --filter='+ *.png' --filter='+ *.gif' --filter='+ *.webp'
    --filter='+ */'
    --filter='- *'
)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG"
}

is_supported_file() {
    local fname="$1"
    case "$fname" in
        .DS_Store|Thumbs.db|~\$*) return 1 ;;
    esac

    case "${fname##*.}" in
        xlsx|xls|xlsb|csv|pptx|ppt|pdf|zip|html|htm|jpg|jpeg|png|gif|webp) return 0 ;;
        *) return 1 ;;
    esac
}

needs_copy() {
    local src="$1"
    local dst="$2"

    if [ ! -f "$dst" ]; then
        return 0
    fi

    local src_size dst_size src_mtime dst_mtime
    src_size=$(stat -f '%z' "$src" 2>/dev/null) || return 0
    dst_size=$(stat -f '%z' "$dst" 2>/dev/null) || return 0
    src_mtime=$(stat -f '%m' "$src" 2>/dev/null) || return 0
    dst_mtime=$(stat -f '%m' "$dst" 2>/dev/null) || return 0

    [ "$src_size" != "$dst_size" ] || [ "$src_mtime" -gt "$dst_mtime" ]
}

copy_gdrive_tree() {
    local src_dir="$1"
    local dst_dir="$2"
    local label="$3"
    local copied=0
    local failed=0
    local src_file fname rel dst_file

    if [ ! -d "$src_dir" ]; then
        return
    fi

    mkdir -p "$dst_dir"

    while IFS= read -r -d '' src_file; do
        fname=${src_file##*/}
        if ! is_supported_file "$fname"; then
            continue
        fi

        rel=${src_file#"$src_dir"/}
        dst_file="$dst_dir/$rel"
        mkdir -p "$(dirname "$dst_file")"

        if needs_copy "$src_file" "$dst_file"; then
            if cp -p "$src_file" "$dst_file" 2>/tmp/sync_nas_cp_error.$$; then
                copied=$((copied + 1))
            else
                failed=$((failed + 1))
                log "WARN: Google Drive ${label} 파일 복사 실패: $src_file ($(cat /tmp/sync_nas_cp_error.$$ 2>/dev/null | head -1))"
            fi
            rm -f /tmp/sync_nas_cp_error.$$
        fi
    done < <(find "$src_dir" -type f -print0 2>/dev/null)

    GDRIVE_COUNT=$((GDRIVE_COUNT + copied))
    if [ "$failed" -gt 0 ]; then
        log "WARN: Google Drive ${label} 복사 실패 ${failed}개"
    fi
}

count_supported_files() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        echo 0
        return
    fi

    find "$dir" -type f \( \
        -name "*.xlsx" -o -name "*.xls" -o -name "*.xlsb" -o \
        -name "*.csv" -o \
        -name "*.pptx" -o -name "*.ppt" -o \
        -name "*.pdf" -o -name "*.zip" -o -name "*.html" -o -name "*.htm" -o \
        -name "*.jpg" -o -name "*.jpeg" -o \
        -name "*.png" -o -name "*.gif" -o -name "*.webp" \
    \) ! -name "~$*" ! -name ".DS_Store" ! -name "Thumbs.db" | wc -l | tr -d ' '
}

copy_with_rclone() {
    local remote="$1"
    local remote_path="$2"
    local dst_dir="$3"
    local label="$4"
    local before after copied
    local out_file="/tmp/sync_nas_rclone.$$"

    if [ -z "$RCLONE_BIN" ]; then
        log "WARN: rclone 미설치 - Google Drive ${label} fallback 사용"
        return 1
    fi

    if ! "$RCLONE_BIN" listremotes | grep -Fxq "$remote"; then
        log "WARN: rclone remote($remote) 미설정 - Google Drive ${label} fallback 사용"
        return 1
    fi

    mkdir -p "$dst_dir"
    before=$(count_supported_files "$dst_dir")

    if "$RCLONE_BIN" copy "${remote}${remote_path}" "$dst_dir" \
        "${RCLONE_FILTERS[@]}" \
        --fast-list \
        --retries 3 \
        --low-level-retries 10 \
        --stats-one-line \
        --log-level INFO >"$out_file" 2>&1; then
        after=$(count_supported_files "$dst_dir")
        copied=$((after - before))
        if [ "$copied" -lt 0 ]; then
            copied=0
        fi
        GDRIVE_COUNT=$((GDRIVE_COUNT + copied))
        log "OK: rclone Google Drive ${label} 복사 완료 (${copied}개 증가)"
        rm -f "$out_file"
        return 0
    fi

    log "WARN: rclone Google Drive ${label} 복사 실패(exit: $?): $(head -3 "$out_file" | tr '\n' ' ')"
    rm -f "$out_file"
    return 1
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    log "SKIP: 이전 동기화 프로세스가 아직 실행 중"
    exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

# === 0. Google Drive → sync 복사 ===
if [ -d "$GDRIVE" ]; then
    GDRIVE_COUNT=0

    # 당일 폴더는 전체 Work Space 스캔보다 먼저 복사한다.
    # Google Drive File Provider가 오래된 큰 파일에서 mmap 오류를 내면 뒤쪽 폴더가 누락될 수 있다.
    TODAY_YEAR=$(date '+%Y')
    TODAY_YM=$(date '+%y%m')
    TODAY_YMD=$(date '+%y%m%d')
    TODAY_GDRIVE="$GDRIVE/Work Space/Download Backup/$TODAY_YEAR/$TODAY_YM/$TODAY_YMD"
    TODAY_SYNC="$SOURCE/Download Backup/$TODAY_YEAR/$TODAY_YM/$TODAY_YMD"
    TODAY_RCLONE="Download Backup/$TODAY_YEAR/$TODAY_YM/$TODAY_YMD"
    TODAY_RCLONE_OK=0
    if copy_with_rclone "$RCLONE_REMOTE" "$TODAY_RCLONE" "$TODAY_SYNC" "당일 폴더"; then
        TODAY_RCLONE_OK=1
    else
        copy_gdrive_tree "$TODAY_GDRIVE" "$TODAY_SYNC" "당일 폴더"
    fi

    # Work Space → sync/ (rclone 당일 폴더 실패 시에만 File Provider 전체 fallback)
    if [ "$TODAY_RCLONE_OK" -ne 1 ] && [ -d "$GDRIVE/Work Space" ]; then
        copy_gdrive_tree "$GDRIVE/Work Space" "$SOURCE" "Work Space"
    fi

    # Screen Shot → sync/Screen Shot/
    if [ -d "$GDRIVE/Screen Shot" ]; then
        if ! copy_with_rclone "$RCLONE_SCREENSHOT_REMOTE" "" "$SOURCE/Screen Shot" "Screen Shot"; then
            copy_gdrive_tree "$GDRIVE/Screen Shot" "$SOURCE/Screen Shot" "Screen Shot"
        fi
    fi

    if [ "$GDRIVE_COUNT" -gt 0 ]; then
        log "OK: Google Drive → sync 복사 (${GDRIVE_COUNT}개 파일)"
    fi
else
    log "WARN: Google Drive 폴더 없음 - 건너뜀"
fi

# === 1. NAS 마운트 확인 ===
if [ ! -d "$NAS_MOUNT" ]; then
    log "NAS 미연결 - 재연결 시도"
    open 'smb://gongbaksoo@192.168.0.235/personal_folder'
    sleep 5
fi

if [ ! -d "$NAS_MOUNT" ]; then
    log "ERROR: NAS 연결 실패 - 다음 스케줄에 재시도"
    exit 1
fi

# === 2. rsync 동기화 (sync → NAS) ===
RSYNC_OUTPUT=$(rsync "${NAS_RSYNC_OPTS[@]}" "${RSYNC_FILTERS[@]}" "$SOURCE" "$NAS_MOUNT" 2>&1)

RSYNC_STATUS=$?

if [ $RSYNC_STATUS -eq 0 ]; then
    SYNC_COUNT=$(echo "$RSYNC_OUTPUT" | grep -c "^>" || true)
    log "OK: 동기화 완료 (전송 파일: ${SYNC_COUNT}개)"
else
    log "ERROR: rsync 실패 (exit code: $RSYNC_STATUS)"
    log "DETAIL: $RSYNC_OUTPUT"
    exit 1
fi

# === 3. 14일 이상 된 로컬 파일 삭제 ===
if [ -d "$SOURCE" ]; then
    DELETE_COUNT=$(find "$SOURCE" -type f \( \
        -name "*.xlsx" -o -name "*.xls" -o -name "*.xlsb" -o \
        -name "*.csv" -o \
        -name "*.pptx" -o -name "*.ppt" -o \
        -name "*.pdf" -o -name "*.zip" -o -name "*.html" -o -name "*.htm" -o \
        -name "*.jpg" -o -name "*.jpeg" -o \
        -name "*.png" -o -name "*.gif" -o -name "*.webp" \
    \) -ctime +14 | wc -l | tr -d ' ')

    if [ "$DELETE_COUNT" -gt 0 ]; then
        find "$SOURCE" -type f \( \
            -name "*.xlsx" -o -name "*.xls" -o -name "*.xlsb" -o \
            -name "*.csv" -o \
            -name "*.pptx" -o -name "*.ppt" -o \
            -name "*.pdf" -o -name "*.zip" -o -name "*.html" -o -name "*.htm" -o \
            -name "*.jpg" -o -name "*.jpeg" -o \
            -name "*.png" -o -name "*.gif" -o -name "*.webp" \
        \) -ctime +14 -delete

        # 빈 디렉토리 정리
        find "$SOURCE" -type d -empty -delete 2>/dev/null

        log "OK: 14일 경과 로컬 파일 삭제 (${DELETE_COUNT}개)"
    fi
fi

# === 4. RAG 자동 인덱싱 (변경 파일만) ===
VENV_PYTHON="$HOME/Desktop/Vibe Coding/nas_sync/.venv/bin/python"
AUTO_INDEX="$HOME/Desktop/Vibe Coding/nas_sync/mcp_rag_server/auto_index.py"
INDEX_LOG="$HOME/.sync_nas_index.log"

if [ -f "$VENV_PYTHON" ] && [ -f "$AUTO_INDEX" ]; then
    if pgrep -f "$AUTO_INDEX" >/dev/null 2>&1; then
        log "SKIP: RAG 인덱싱 이미 실행 중"
    else
        nohup "$VENV_PYTHON" "$AUTO_INDEX" >> "$INDEX_LOG" 2>&1 &
        log "OK: RAG 인덱싱 백그라운드 시작 (pid: $!)"
    fi
else
    log "SKIP: RAG 인덱싱 스크립트 없음"
fi

log "--- 동기화 사이클 완료 ---"
