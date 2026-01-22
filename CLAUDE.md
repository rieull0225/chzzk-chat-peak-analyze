# NokChart 프로젝트 컨텍스트

> 이 파일은 Claude가 프로젝트를 이해하기 위한 컨텍스트입니다. 지속적으로 갱신됩니다.

## 프로젝트 개요

**NokChart**는 치지직(Chzzk) 라이브 스트림의 채팅 추이를 수집, 분석, 시각화하는 도구입니다.

### 핵심 기능
- 자동 방송 모니터링 (여러 채널 동시 감시)
- 채팅/도네이션 실시간 수집 (WebSocket)
- 2단계 피크 탐지 (10초 대략 + 1초 정밀)
- 토픽 분석 (한국어 키워드 추출)
- 시각화 차트 생성

## 기술 스택

| 항목 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| CLI | Click |
| 비동기 | aiohttp, asyncio |
| 데이터 | pandas, Pydantic |
| 시각화 | matplotlib |
| 형태소 | kiwipiepy (선택) |
| 배포 | Docker, GCP e2-micro |

## 디렉토리 구조

```
nokchart/
├── cli.py              # CLI 커맨드 (watch, collect, process, stats)
├── watcher.py          # 채널 상태 폴링 및 수집기 관리
├── collector.py        # 스트림별 이벤트 수집
├── models.py           # Pydantic 데이터 모델
├── aggregation.py      # 시계열 생성 (1s, 60s, 300s 버킷)
├── peak_detection.py   # 2단계 피크 탐지
├── topic_analysis.py   # 한국어 키워드 추출
├── visualization.py    # 차트 생성
└── chat/               # WebSocket 채팅 클라이언트
    ├── client.py       # 재연결 로직 포함
    ├── websocket.py    # aiohttp WebSocket
    ├── http.py         # HTTP API (상태 조회)
    └── reconnect.py    # 지수 백오프 재연결
```

## 주요 CLI 명령어

```bash
nokchart watch --channels channels.yaml --config config.yaml  # 자동 모니터링
nokchart collect --channel-id <ID>                            # 수동 수집
nokchart process --stream-dir <DIR> --stream-id <ID>          # 데이터 처리
nokchart stats                                                # 수집 통계
```

## GCP 배포

### VM 정보
- **프로젝트**: chzzk-chat-receiver
- **인스턴스**: instance-20260108-152205
- **Zone**: us-west1-a
- **타입**: e2-micro (무료 티어)

### 배포 명령어
```bash
# 로컬에서 GCP로 배포
git push origin main
gcloud compute ssh minjunpark@instance-20260108-152205 \
  --project="chzzk-chat-receiver" \
  --zone="us-west1-a" \
  --command="cd nokchart && git pull && sudo docker compose down && sudo docker compose up -d --build"
```

### 동기화
```bash
# GCP → 로컬 동기화 (alias: sync-nok)
~/nokchart/scripts/sync-nokchart.sh
```

## 모니터링 채널

| 채널 ID | 방송인 |
|---------|--------|
| b6845db9a47441227410125f581eee31 | 마로카 |
| 7c4c49fd3a34ce68e84075f5b44fe8c8 | 네무 |
| 37716364b3086fefd298046072c92345 | 미라이 |
| acc87c975763452aab25e281e0eb0b85 | 루비 |
| cb40b98631410d4cc3796ab279c2f1bc | 바레사 |
| 10d1ce368f685df0502875195eee39eb | 이리야 |
| c3702f874360da3f81ae24ddf1f0343e | 체리 |
| 9d1aaaca8c18fd5e4d25ea19710ad789 | 엘라 |

## 최근 변경사항

### 2026-01-23
- **하루 여러 방송 수집 버그 수정**: `live_id`로 새 방송 감지
  - `StreamInfo`에 `live_id` 필드 추가
  - 수집 중인 채널도 계속 체크하여 `live_id` 변경 시 새 수집 시작
- **Docker 안정성 개선**
  - `restart: always`로 변경
  - healthcheck 추가 (60초 간격, 프로세스 모니터링)

### 이전 주요 변경
- 2단계 피크 탐지 추가 (10s rough + 1s precise)
- 시계열 버킷 60s → 10s 변경
- 채널 폴링 견고성 강화
- 라이브 감지 후 클라이언트 상태 리셋

## 알려진 이슈

1. **데이터 유실 가능성**: Docker 컨테이너가 예기치 않게 종료되면 진행 중인 수집 데이터가 처리되지 않음
   - 해결: healthcheck + restart:always 적용됨

2. **채널 "not found" 로그**: 오프라인 채널도 "not found"로 로깅됨 (혼란스러움)
   - TODO: 로그 메시지 개선 필요

## 유용한 명령어

```bash
# GCP 컨테이너 로그 확인
gcloud compute ssh ... --command="sudo docker logs nokchart --tail 50"

# GCP 컨테이너 상태 확인
gcloud compute ssh ... --command="sudo docker ps"

# 로컬에서 테스트 실행
nokchart watch --channels channels.yaml --config config.yaml

# 특정 스트림 수동 처리
nokchart process --stream-dir output/2026-01-22/이리야_... --stream-id 이리야_...
```

---
*마지막 업데이트: 2026-01-23*
