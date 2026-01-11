#!/bin/bash
# GCP VM에서 로컬로 데이터 동기화 및 자동 분석

PROJECT="chzzk-chat-receiver"
INSTANCE="instance-20260108-152205"
ZONE="us-west1-a"
REMOTE_PATH="chzzk-chat-peak-analyze/output"
LOCAL_PATH="$HOME/nokchart/output-gcp"

echo "$(date): Syncing data from GCP VM..."
mkdir -p "$LOCAL_PATH"

# gcloud 경로 로드
source ~/google-cloud-sdk/path.zsh.inc

# GCP → 로컬 동기화
gcloud compute scp --recurse \
  --project="$PROJECT" \
  --zone="$ZONE" \
  "mangnaniee@${INSTANCE}:${REMOTE_PATH}" \
  "${LOCAL_PATH}" 2>&1 | grep -v "WARNING"

echo "$(date): Sync completed"

# 동기화 후 중복 폴더 정리 (unknown_ 폴더 제거)
echo "$(date): Cleaning up duplicate folders..."
find "${LOCAL_PATH}/output" -type d -name "unknown_*" -exec rm -rf {} + 2>/dev/null || true
find "${LOCAL_PATH}/output" -type d -name "*_unknown_*" -exec rm -rf {} + 2>/dev/null || true
echo "$(date): Cleanup completed"

# unknown_ 폴더 리네임 (채널 ID → 방송인 이름)
echo "$(date): Renaming unknown_ folders..."

# 채널 ID → 방송인 이름 매핑 함수
get_streamer_name() {
    local channel_id="$1"
    case "$channel_id" in
        "b6845db9a47441227410125f581eee31") echo "마로카" ;;
        "7c4c49fd3a34ce68e84075f5b44fe8c8") echo "네무" ;;
        "37716364b3086fefd298046072c92345") echo "미라이" ;;
        "acc87c975763452aab25e281e0eb0b85") echo "루비" ;;
        "cb40b98631410d4cc3796ab279c2f1bc") echo "바레사" ;;
        "10d1ce368f685df0502875195eee39eb") echo "이리야" ;;
        "c3702f874360da3f81ae24ddf1f0343e") echo "체리" ;;
        "9d1aaaca8c18fd5e4d25ea19710ad789") echo "엘라" ;;
        *) echo "" ;;
    esac
}

# unknown_으로 시작하는 폴더 찾기
find "${LOCAL_PATH}/output" -type d -name "unknown_*" | while read -r dir; do
    dir_name=$(basename "$dir")

    # unknown_ 제거하여 나머지 추출
    # 형식: unknown_150030_b6845db9a47441227410125f581eee31
    # → 150030_b6845db9a47441227410125f581eee31
    rest="${dir_name#unknown_}"

    # 채널 ID 추출 (마지막 32자리)
    channel_id="${rest: -32}"

    # 매핑에서 방송인 이름 찾기
    streamer_name=$(get_streamer_name "$channel_id")

    if [ -n "$streamer_name" ]; then
        # 새 이름: 마로카_150030_b6845...
        new_name="${streamer_name}_${rest}"
        parent_dir=$(dirname "$dir")
        new_path="${parent_dir}/${new_name}"

        # 이미 리네임된 폴더가 없으면 리네임
        if [ ! -d "$new_path" ]; then
            echo "  Renaming: $dir_name -> $new_name"
            mv "$dir" "$new_path"
        fi
    fi
done

echo "$(date): Renaming completed"

# 동기화된 데이터 분석 (peaks + 차트 생성)
echo "$(date): Processing streams..."

cd "$HOME/nokchart"

# output/2026-01-*/스트리머_* 형태의 모든 스트림 디렉토리 찾기
find "${LOCAL_PATH}/output" -type d -name "*_*" | while read -r stream_dir; do
    # events.jsonl이 있는지 확인
    if [ ! -f "$stream_dir/events.jsonl" ]; then
        continue
    fi
    
    # peaks.json이 이미 있으면 스킵
    if [ -f "$stream_dir/peaks.json" ]; then
        continue
    fi
    
    # 스트림 ID 추출 (디렉토리 이름)
    stream_id=$(basename "$stream_dir")
    
    echo "  Processing: $stream_id"
    
    # nokchart process 실행 (시계열 + 피크 + 차트)
    python3 -m nokchart.cli process \
        --stream-dir "$stream_dir" \
        --stream-id "$stream_id" 2>&1 | grep -E "(Processing|Created|Found|complete)"
done

echo "$(date): All done!"
