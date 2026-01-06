# NokChart

치지직 스트림을 위한 채팅 추이 수집, 피크 분석 및 시각화 도구입니다.

NokChart는 치지직 채널을 자동으로 모니터링하고, 방송이 시작되면 채팅 이벤트를 수집하며, 채팅 활동 피크를 분석하고 시각화 차트를 생성합니다.

## 주요 기능

- **자동 방송 모니터링**: 여러 채널을 감시하고 방송이 시작되면 자동으로 수집 시작
- **채팅 이벤트 수집**: 정확한 타임스탬프와 함께 채팅 메시지 및 도네이션 수집
- **피크 탐지**: 슬라이딩 윈도우 분석을 사용하여 높은 활동성을 보이는 채팅 구간 식별
- **시계열 생성**: 1초, 5초, 60초 단위 시계열 및 이동 평균 생성
- **시각화**: 피크 구간이 강조된 채팅 활동 추이 PNG 차트 생성
- **표준 출력 형식**: 표준화된 스키마로 `events.jsonl`, `peaks.json`, `chat_ts_*.csv` 출력

## 설치

```bash
# 저장소로 이동
cd nokchart

# 의존성 설치 (Python 3.11+ 필요)
python3.11 -m pip install -e .

# 개발용
python3.11 -m pip install -e ".[dev]"
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

API 인증 정보를 추가하고 수집 파라미터를 조정합니다:

```yaml
# 치지직 API 인증 정보
chzzk_client_id: "여기에_CLIENT_ID_입력"
chzzk_client_secret: "여기에_CLIENT_SECRET_입력"

# Watcher 설정
poll_interval_sec: 60  # 방송 상태 확인 주기
restart_resume: true   # 재시작 시 수집 재개

# 피크 탐지 설정
peak_window_sec: 60    # 피크 탐지 윈도우 크기
topk: 50               # 추출할 상위 피크 개수
min_peak_gap_sec: 120  # 피크 간 최소 간격

# 집계 설정
rolling_sec: 10        # 이동 평균 윈도우

# 출력 설정
outdir: "output"       # 기본 출력 디렉토리
```

### 3단계: channels.yaml 설정

모니터링할 채널을 설정합니다:

```yaml
channels:
  - "channel_id_1"
  - "channel_id_2"
```

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

각 스트림마다 NokChart는 다음을 생성합니다:

```
output/
└── <stream_id>/
    ├── events.jsonl              # 원시 채팅 이벤트 (JSONL 형식)
    ├── chat_ts_1s.csv            # 1초 단위 시계열
    ├── chat_ts_5s.csv            # 5초 단위 시계열
    ├── chat_ts_60s.csv           # 60초 단위 시계열
    ├── peaks.json                # 탐지된 채팅 피크
    ├── chart_chat_rate.png       # 시각화 차트
    ├── collection_report.json    # 수집 메타데이터
    └── report.json               # 처리 보고서
```

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

### chat_ts_1s.csv

시계열 데이터:

```csv
sec,chat_count,chat_count_rolling_10s
0,5,5.0
1,8,6.5
2,12,8.3
```

## 중요 사항

### API 구현

이 도구는 치지직 API와 상호작용하기 위해 **공식 [chzzkpy](https://pypi.org/project/chzzkpy/)** 라이브러리를 사용합니다:

- ✅ 공식 치지직 API 엔드포인트 사용
- ✅ [치지직 개발자센터](https://developers.chzzk.naver.com)에서 받은 적절한 API 인증 정보 필요
- ✅ DRM 우회나 비공식 스크래핑 없음
- ✅ 플랫폼 이용약관 완전 준수

`collector.py`의 `ChzzkClient`는 chzzkpy를 사용하여 구현되었으며 다음을 처리합니다:
- `get_stream_status()`: 공식 API를 사용하여 채널 라이브 여부 확인
- `connect_chat()`: 공식 WebSocket 연결을 사용하여 채팅 스트림에 연결

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

### "Chzzk API credentials not provided" 오류

1. `config.yaml`에 인증 정보를 추가했는지 확인:
   ```yaml
   chzzk_client_id: "실제_client_id"
   chzzk_client_secret: "실제_client_secret"
   ```
2. [치지직 개발자센터](https://developers.chzzk.naver.com)에서 인증 정보 받기

### OAuth 인증 오류

**리디렉션 URL 불일치**:
- 개발자센터에서 리디렉션 URL을 정확히 `http://localhost:8080`으로 설정했는지 확인
- URL은 대소문자 구분하며, 끝에 슬래시(/)를 붙이지 않습니다

**인증 코드 오류**:
- 리디렉션 URL 전체가 아닌 `code=` 뒤의 값만 복사했는지 확인
- 예시: `http://localhost:8080/?code=ABC123&state=...`에서 `ABC123` 부분만 입력
- 인증 코드는 일정 시간 후 만료되므로 빠르게 입력해야 합니다

### 이벤트가 수집되지 않음

1. 채널 ID가 올바른지 확인
2. 스트림이 실제로 라이브 중인지 확인
3. API 인증 정보가 유효한지 확인
4. 네트워크 연결 확인

### 피크가 탐지되지 않음

1. `chat_ts_1s.csv`에 데이터가 있는지 확인
2. 채팅 활동이 충분히 높았는지 확인
3. `peak_window_sec` 또는 `min_peak_gap_sec` 파라미터 조정

### 차트 생성 실패

1. matplotlib이 설치되어 있는지 확인
2. 시계열 파일이 존재하고 유효한 데이터가 있는지 확인
3. 출력 디렉토리에 쓰기 권한이 있는지 확인
