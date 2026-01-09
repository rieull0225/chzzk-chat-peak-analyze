# NokChart

치지직 스트림을 위한 채팅 추이 수집, 피크 분석 및 시각화 도구입니다.

NokChart는 치지직 채널을 자동으로 모니터링하고, 방송이 시작되면 채팅 이벤트를 수집하며, 채팅 활동 피크를 분석하고 시각화 차트를 생성합니다.

## 주요 기능

- **자동 방송 모니터링**: 여러 채널을 감시하고 방송이 시작되면 자동으로 수집 시작
- **채팅 이벤트 수집**: 정확한 타임스탬프와 함께 채팅 메시지 및 도네이션 수집
- **강력한 WebSocket 안정성**:
  - 자동 재연결 (지수 백오프, 최대 100회 시도)
  - 하트비트 모니터링 (58초 타임아웃)
  - 브라우저 헤더 스푸핑으로 연결 안정성 향상
  - 장시간 방송(6시간+) 동안 끊김 없는 채팅 수집
- **통계 조회**: `nokchart stats` 명령어로 수집 현황 실시간 확인
- **피크 탐지**: 슬라이딩 윈도우 분석을 사용하여 높은 활동성을 보이는 채팅 구간 식별
- **시계열 생성**: 1분, 5분 단위 시계열 및 이동 평균 생성
- **시각화**: 피크 구간이 강조된 채팅 활동 추이 PNG 차트 생성 (실제 방송 시간 표시)
- **날짜별 정리**: 날짜별 폴더에 방송인 이름이 포함된 디렉토리로 자동 정리
- **Docker 지원**: Docker Compose로 간편한 배포 및 실행
- **클라우드 배포**: GCP 무료 티어(e2-micro)에서 24시간 안정적 운영
- **표준 출력 형식**: 표준화된 스키마로 `events.jsonl`, `peaks.json`, `chat_ts_*.csv` 출력

## 빠른 시작 (Docker - 권장)

Docker를 사용하면 Python 환경 설정 없이 바로 사용할 수 있습니다.

### 1. 저장소 클론

```bash
git clone https://github.com/rieull0225/chzzk-chat-peak-analyze.git
cd chzzk-chat-peak-analyze
```

### 2. 설정 파일 생성

```bash
# 예시 파일을 복사해서 실제 설정 파일 생성
cp config.example.yaml config.yaml
cp channels.example.yaml channels.yaml
```

### 3. 설정 파일 수정

`config.yaml`에 API 키 입력:
```yaml
chzzk_client_id: "여기에_CLIENT_ID_입력"
chzzk_client_secret: "여기에_CLIENT_SECRET_입력"
```

`channels.yaml`에 모니터링할 채널 입력:
```yaml
channels:
  - "채널ID1"  # 방송인1
  - "채널ID2"  # 방송인2
```

### 4. Docker 실행

```bash
docker-compose up -d
```

### 5. 로그 확인

```bash
docker logs -f nokchart
```

### 6. 수집 중단

```bash
docker-compose down
```

## 클라우드 배포 (GCP 무료 티어)

24시간 안정적인 수집을 위해 GCP e2-micro 인스턴스(무료)에 배포할 수 있습니다.

### GCP VM 설정

```bash
# 1. GCP e2-micro 인스턴스 생성 (us-west1 리전 - 무료)
# 2. VM에 SSH 접속
# 3. Docker 설치
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo apt-get install -y docker-compose-plugin

# 4. 프로젝트 클론 및 실행
git clone https://github.com/rieull0225/chzzk-chat-peak-analyze.git
cd chzzk-chat-peak-analyze
# config.yaml, channels.yaml 설정
docker compose up -d
```

### 로컬과 동기화

로컬 맥북에서 GCP VM 데이터를 주기적으로 가져옵니다:

```bash
# 동기화 스크립트 사용 (프로젝트 내 포함)
# scripts/sync-nokchart.sh를 수정하여 PROJECT, INSTANCE, ZONE 설정

# 수동 실행
./scripts/sync-nokchart.sh

# 매시간 자동 동기화 (크론잡)
(crontab -l 2>/dev/null; echo "0 * * * * cd $HOME/nokchart && ./scripts/sync-nokchart.sh >> $HOME/nokchart/sync.log 2>&1") | crontab -
```

**동기화 스크립트 기능:**
- GCP VM에서 로컬로 output 폴더 동기화
- `unknown_*` 폴더를 자동으로 `방송인이름_*` 형식으로 리네임
- 새로 수집된 스트림 자동 분석 (시계열, 피크 감지, 차트 생성)

## 로컬 설치 (수동)

Docker 없이 직접 실행하려면:

```bash
# Python 3.11+ 필요
python3.11 -m pip install -e .

# 실행
nokchart watch --channels channels.yaml --config config.yaml
```

## 설정

### 1단계: 치지직 API 인증 정보 받기

1. [치지직 개발자센터](https://developers.chzzk.naver.com) 접속
2. 새 애플리케이션 생성
3. **중요**: 리디렉션 URL을 `http://localhost:8080`으로 설정
4. `Client ID`와 `Client Secret` 받기

**OAuth 인증 흐름**:
- NokChart는 OAuth2 인증을 사용합니다
- 처음 실행 시 브라우저에서 로그인해야 합니다
- 인증 과정:
  1. 프로그램이 인증 URL을 출력합니다
  2. 브라우저에서 해당 URL을 열어 로그인합니다
  3. 로그인 후 리디렉션 URL(http://localhost:8080/?code=...)에서 `code=` 뒤의 인증 코드를 복사합니다
  4. 프로그램에 인증 코드를 입력합니다
- 인증은 세션당 한 번만 필요합니다

### 2단계: config.yaml 설정

`config.example.yaml`을 `config.yaml`로 복사하고 설정을 조정합니다:

```yaml
# 치지직 API 인증 정보
chzzk_client_id: "여기에_CLIENT_ID_입력"
chzzk_client_secret: "여기에_CLIENT_SECRET_입력"

# Watcher 설정
poll_interval_sec: 60           # 방송 상태 확인 주기 (초)
restart_resume: true            # 재시작 시 수집 재개
idle_timeout_minutes: 30        # 채팅이 없으면 N분 후 자동 종료 및 데이터 처리

# 피크 탐지 설정
peak_window_sec: 60             # 피크 탐지 윈도우 크기 (초)
topk: 50                        # 추출할 상위 피크 개수
min_peak_gap_sec: 120           # 피크 간 최소 간격 (초)

# 집계 설정
rolling_sec: 600                # 이동 평균 윈도우 (10분)

# 출력 설정
outdir: "output"                # 기본 출력 디렉토리

# 재시도 설정
max_retries: 5
backoff_factor: 2
```

### 3단계: channels.yaml 설정

`channels.example.yaml`을 `channels.yaml`로 복사하고 모니터링할 채널을 설정합니다:

```yaml
channels:
  - "채널ID1"  # 방송인1
  - "채널ID2"  # 방송인2
  - "채널ID3"  # 방송인3
```

**채널 ID 찾는 법**:
1. 치지직 채널 페이지 접속
2. URL에서 ID 확인: `https://chzzk.naver.com/live/채널ID`

## 사용법

### 자동 모니터링 (권장)

설정된 채널을 감시하고 방송이 시작되면 자동으로 수집합니다:

```bash
nokchart watch --channels channels.yaml --config config.yaml
```

이 명령은:
1. 60초마다 각 채널 폴링 (설정 가능)
2. OFFLINE→LIVE 전환 감지
3. 자동으로 채팅 이벤트 수집 시작
4. 방송 종료 시 수집 중단
5. 모든 출력 파일 자동 생성

### 수집 통계 확인

실시간으로 수집 현황을 확인합니다:

```bash
# 모든 수집 데이터 통계
nokchart stats

# 특정 날짜만 확인
nokchart stats --date 2026-01-08

# 특정 output 디렉토리 확인
nokchart stats --output output-gcp
```

출력 예시:
```
================================================================================
  📊 NokChart Collection Statistics
================================================================================

📅 2026-01-08
📁 스트리머_unknown_xxxxxx

  ⏱️  방송 시간: 13:00:00 ~ 15:30:00 (150.0분)
  💬 채팅 수: 10,000개
  💰 후원 수: 50개
  📈 분당 채팅: 66.7개/분
  ✅ 재연결: 0회
```

### 기존 수집 데이터 처리

이미 `events.jsonl`이 있는 스트림 디렉토리를 처리합니다:

```bash
nokchart process --stream-dir output/stream_123 --stream-id stream_123
```

이 명령은:
1. 이벤트로부터 시계열 생성
2. 피크 탐지
3. 시각화 차트 생성
4. report.json 생성

### 수동 단계별 실행

각 단계를 개별적으로 실행할 수도 있습니다:

#### 시계열 생성

```bash
nokchart build-ts --events output/stream_123/events.jsonl --out output/stream_123
```

#### 피크 탐지

```bash
nokchart peaks --ts output/stream_123/chat_ts_1s.csv --stream-id stream_123 --out output/stream_123/peaks.json
```

#### 차트 생성

```bash
nokchart plot --ts output/stream_123/chat_ts_1s.csv --peaks output/stream_123/peaks.json --out output/stream_123/chart.png
```

## 출력 구조

NokChart는 날짜별로 폴더를 생성하고, 각 스트림마다 방송인 이름이 포함된 디렉토리에 데이터를 저장합니다:

```
output/
├── 2026-01-06/                          # 날짜별 폴더
│   ├── 미라이_unknown_37716.../          # 방송인 이름_스트림ID
│   │   ├── events.jsonl                # 원시 채팅 이벤트 (JSONL 형식)
│   │   ├── chat_ts_60s.csv             # 1분 단위 시계열
│   │   ├── chat_ts_300s.csv            # 5분 단위 시계열
│   │   ├── peaks.json                  # 탐지된 채팅 피크
│   │   ├── chart_chat_rate.png         # 시각화 차트 (실제 방송 시간 표시)
│   │   ├── collection_report.json      # 수집 메타데이터
│   │   └── report.json                 # 처리 보고서
│   └── 바레사_unknown_cb40b.../
│       └── ...
├── 2026-01-07/                          # 다음 날
│   └── ...
└── ...
```

**장점**:
- 📅 날짜별로 자동 정리
- 👤 방송인 이름으로 쉽게 식별
- 🔍 같은 방송인의 여러 방송도 스트림 ID로 구분

## 출력 스키마

### events.jsonl

각 줄은 JSON 형식의 단일 이벤트를 포함합니다:

```json
{"stream_id":"S123","type":"chat","t_ms":1234567,"user":"사용자명","text":"메시지","received_at":"2024-01-01T12:00:00Z"}
{"stream_id":"S123","type":"donation","t_ms":1237890,"amount":10000,"text":"후원 메시지","received_at":"2024-01-01T12:01:00Z"}
```

### peaks.json

피크 탐지 결과:

```json
{
  "stream_id": "S123",
  "window_sec": 60,
  "peaks": [
    {
      "start_sec": 742,
      "end_sec": 802,
      "value": 156,
      "rank": 1
    },
    {
      "start_sec": 1290,
      "end_sec": 1350,
      "value": 141,
      "rank": 2
    }
  ]
}
```

### chat_ts_60s.csv

1분 단위 시계열 데이터:

```csv
sec,chat_count,timestamp,chat_count_rolling_600s
0,150,2026-01-06T12:00:00+00:00,150.0
60,180,2026-01-06T12:01:00+00:00,165.0
120,200,2026-01-06T12:02:00+00:00,176.7
```

- `sec`: 방송 시작 후 경과 시간 (초)
- `chat_count`: 해당 1분 동안의 채팅 개수
- `timestamp`: 실제 방송 시간
- `chat_count_rolling_600s`: 10분 이동 평균

## 기술 스택

- **Python 3.11+**: 메인 프로그래밍 언어
- **[chzzkpy](https://pypi.org/project/chzzkpy/)**: 공식 치지직 API 라이브러리
- **asyncio**: 비동기 I/O 및 멀티채널 모니터링
- **pandas**: 시계열 데이터 처리 및 집계
- **matplotlib**: 채팅 활동 차트 시각화
- **pydantic**: 데이터 검증 및 스키마 정의
- **Docker**: 컨테이너화된 배포

## 중요 사항

### API 구현

이 도구는 치지직 API와 상호작용하기 위해 **공식 [chzzkpy](https://pypi.org/project/chzzkpy/)** 라이브러리를 사용합니다:

- ✅ 공식 치지직 API 엔드포인트 사용
- ✅ [치지직 개발자센터](https://developers.chzzk.naver.com)에서 받은 적절한 API 인증 정보 필요
- ✅ DRM 우회나 비공식 스크래핑 없음
- ✅ 플랫폼 이용약관 완전 준수

`collector.py`의 `ChzzkChannelClient`는 chzzkpy를 사용하여 구현되었으며 다음을 처리합니다:
- `get_stream_status()`: 공식 API를 사용하여 채널 라이브 여부 확인
- `connect_chat()`: 공식 WebSocket 연결을 사용하여 채팅 스트림에 연결
- 세션 재사용으로 장시간 안정적인 채팅 수집

### 안전 및 정책

- 승인/합법적인 범위 내에서만 이 도구 사용
- 플랫폼 이용약관 준수
- 치지직 개발자센터의 유효한 API 인증 정보 필요
- 수집된 데이터는 개인 용도로만 사용

## 개발

### 테스트 실행

```bash
pytest tests/
```

### 코드 품질

```bash
# 코드 포맷팅
black nokchart/

# 린팅
ruff check nokchart/
```

## AutoKirinuki와 통합

NokChart 출력물은 AutoKirinuki (VOD 편집 자동화 도구)의 입력으로 사용되도록 설계되었습니다:

- `peaks.json` → 테마 탐지 및 컷 선택에 사용
- `events.jsonl` → 편집 결정을 위한 추가 컨텍스트
- `chat_ts_1s.csv` → 활동 패턴을 위한 시계열 분석

## 라이선스

이 도구는 교육 및 승인된 용도로만 제공됩니다.

## 문제 해결

### 수집 현황 확인

실시간으로 수집된 채팅 개수를 확인하려면:

```bash
# 모든 스트림의 이벤트 개수 확인
find output -name "events.jsonl" -type f -exec sh -c '
    dir=$(dirname "{}");
    dirname=$(basename "$dir");
    count=$(wc -l < "{}" 2>/dev/null || echo "0");
    echo "$dirname: $count 개"
' \; | sort

# 특정 스트림만 실시간 모니터링
watch -n 1 'wc -l output/2026-01-06/미라이_*/events.jsonl'
```

### "Session is closed" 오류

이전 버전에서 발생했던 세션 종료 버그는 수정되었습니다. 최신 버전을 사용하세요:
```bash
git pull origin main
docker-compose down && docker-compose build && docker-compose up -d
```

### 채팅이 2~3분 후 중단됨

status check 클라이언트가 채팅 클라이언트의 세션을 종료시키는 문제는 수정되었습니다. 이제 6시간+ 방송도 안정적으로 수집됩니다.

### Docker 관련 문제

**컨테이너가 시작되지 않음**:
```bash
# 로그 확인
docker logs nokchart

# 컨테이너 재시작
docker-compose restart

# 완전히 새로 시작
docker-compose down && docker-compose up -d
```

**볼륨 권한 문제**:
```bash
# output 디렉토리 권한 확인
ls -la output/

# 권한 수정 (필요시)
chmod -R 755 output/
```

### API 인증 문제

**"Chzzk API credentials not provided" 오류**:
1. `config.yaml`에 인증 정보를 추가했는지 확인
2. [치지직 개발자센터](https://developers.chzzk.naver.com)에서 인증 정보 받기

**채널을 찾을 수 없음**:
1. 채널 ID가 정확한지 확인
2. 해당 채널이 실제로 방송 중인지 확인

### 성능 문제

**메모리 사용량이 높음**:
- 6개 채널을 동시에 모니터링하면 정상적으로 메모리 사용량이 증가합니다
- 필요 없는 채널은 `channels.yaml`에서 제거하세요

**CPU 사용량이 높음**:
- `poll_interval_sec`를 늘려서 체크 빈도를 낮추세요 (예: 60 → 120)
