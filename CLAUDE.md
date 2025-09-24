# CLAUDE.md - 개발자 기술 문서

## 프로젝트 개요

**SHT 듀얼 LIVE 카메라** - 라즈베리파이 5 기반 듀얼 카메라 CCTV 시스템
- **목적**: 실시간 CCTV 스트리밍 + 24시간 자동 녹화
- **핵심**: FastAPI + Picamera2 GPU 가속 + 통합 아키텍처
- **특징**: 웹 스트리밍과 연속 녹화 독립 동작

## 시스템 아키텍처

### 기술 스택
- **하드웨어**: Raspberry Pi 5 (BCM2712), OV5647 카메라 × 2
- **백엔드**: FastAPI + Picamera2 + GPU H.264 인코딩
- **프론트엔드**: Vanilla JS + 반응형 UI + 실시간 모니터링
- **스토리지**: 30초 단위 MP4 파일 자동 저장

### 파일 구조
```
livecam/
├── webmain.py             # 통합 메인 서버 (스트리밍 + 녹화)
├── config_manager.py      # 설정 관리자 모듈
├── config.json            # JSON 설정 파일
├── web/                   # 웹 인터페이스
│   ├── static/
│   │   ├── index.html     # 듀얼 뷰 메인 페이지
│   │   ├── style.css      # 스타일시트
│   │   └── script.js      # 클라이언트 로직
│   └── api.py             # FastAPI 라우터
├── videos/                # 녹화 파일 저장소
│   ├── cam0/              # 카메라 0 녹화 파일
│   └── cam1/              # 카메라 1 녹화 파일
├── README.md              # 사용자 가이드
└── CLAUDE.md              # 개발자 문서 (현재 파일)
```

## 핵심 기능

### 1. 실시간 웹 스트리밍
- **MJPEG 스트리밍**: 30fps, 다중 클라이언트 지원 (최대 2명)
- **듀얼/싱글 뷰**: 실시간 전환, 카메라 개별 제어
- **해상도 지원**: 640×480 (480p), 1280×720 (720p)
- **거울모드**: 좌우 반전 (`libcamera.Transform(hflip=True)`)

### 2. 24시간 자동 녹화
- **연속 녹화**: 30초 단위 끊김없는 녹화 (24/7)
- **GPU 가속**: H.264 하드웨어 인코딩 (5Mbps, 30fps)
- **독립 동작**: 웹 접속과 무관하게 백그라운드 동작
- **자동 관리**: 타임스탬프 파일명, 실시간 통계

### 3. 웹 인터페이스
- **실시간 모니터링**: LIVE/OFFLINE 상태, FPS, 프레임 수
- **직관적 컨트롤**: 카메라 전환, 해상도 변경
- **반응형 디자인**: 모바일/데스크톱 지원
- **하트비트 체크**: 3초 간격 연결 상태 확인

### 4. JSON 설정 시스템
- **유연한 설정 관리**: config.json 파일로 모든 설정 중앙화
- **실시간 적용**: 서버 재시작 없이 설정 변경 가능
- **기본값 제공**: 누락된 설정은 자동으로 기본값 적용
- **점 표기법**: `recording.bitrate` 형태로 직관적 접근

## 핵심 클래스

### 1. CameraManager
**역할**: 카메라 스트리밍 및 모드 관리
```python
class CameraManager:
    def start_camera_stream(self, camera_id: int) -> bool
    def enable_dual_mode(self) -> bool
    def generate_stream(self, client_ip: str, camera_id: int = None)
    def get_stats(self) -> Dict[str, Any]
```

### 2. GPURecorder
**역할**: GPU 가속 연속 녹화
```python
class GPURecorder:
    def start_continuous_recording(self, interval: int = 31)
    def _record_single_video(self, duration: int = 31)
    def stop_recording(self)
```

### 3. CCTVWebAPI
**역할**: FastAPI 라우팅 및 API 엔드포인트
```python
class CCTVWebAPI:
    @app.get("/stream/{camera_id}")
    @app.post("/api/dual_mode/{enable}")
    @app.get("/api/stats")
```

### 4. ConfigManager
**역할**: JSON 설정 파일 관리
```python
class ConfigManager:
    def get(self, path: str, default=None) -> Any
    def set(self, path: str, value: Any) -> bool
    def get_bitrate(self) -> int
    def get_segment_duration(self) -> int
    def reload(self) -> bool
```

## JSON 설정 시스템

### config.json 구조
```json
{
  "recording": {
    "enabled": true,
    "segment_duration": 31,      // 녹화 세그먼트 길이 (초)
    "overlap_duration": 1,       // 세그먼트 오버랩 (초)
    "bitrate": 5000000,          // 비트레이트 (bps)
    "framerate": 30,             // 프레임레이트 (fps)
    "resolution": [640, 480],    // 해상도 [가로, 세로]
    "cameras": {
      "0": {
        "enabled": true,
        "storage_path": "videos/cam0"
      },
      "1": {
        "enabled": true,
        "storage_path": "videos/cam1"
      }
    },
    "cleanup": {
      "enabled": false,          // 자동 정리 기능
      "max_age_days": 30,        // 최대 보관 일수
      "min_free_space_gb": 10    // 최소 여유 공간 (GB)
    }
  },
  "streaming": {
    "max_clients": 2,            // 최대 동시 접속자 수
    "default_quality": "640x480",
    "mirror_mode": true,         // 거울모드 활성화
    "buffer_size": 10,           // 스트림 버퍼 크기
    "stats_interval": 2000,      // 통계 업데이트 간격 (ms)
    "heartbeat_interval": 3000   // 하트비트 체크 간격 (ms)
  },
  "system": {
    "web_port": 8001,           // 웹 서버 포트
    "log_level": "INFO",        // 로그 레벨
    "gpu_memory_split": 256     // GPU 메모리 할당 (MB)
  }
}
```

### ConfigManager 사용법
```python
from config_manager import config_manager

# 기본 사용법
segment_duration = config_manager.get_segment_duration()  # 31
bitrate = config_manager.get_bitrate()                    # 5000000

# 점 표기법으로 직접 접근
port = config_manager.get('system.web_port', 8001)       # 8001
mirror = config_manager.get('streaming.mirror_mode')     # True

# 설정 변경
config_manager.set('recording.bitrate', 8000000)
config_manager.save_config()

# 설정 리로드
config_manager.reload()
```

### 설정 변경 방법
1. **파일 직접 수정**: `config.json` 파일을 편집
2. **프로그래밍 방식**: ConfigManager의 `set()` 메서드 사용
3. **실시간 적용**: 대부분 설정은 다음 동작 시 자동 적용

## 중요 설정

### 카메라 구성
```python
config = picam2.create_video_configuration(
    main={
        "size": (width, height),
        "format": "YUV420"         # H.264 녹화 최적화
    },
    lores={
        "size": (width, height),
        "format": "RGB888"         # MJPEG 스트리밍
    },
    buffer_count=2,                # 레이턴시 최소화
    queue=False,
    transform=libcamera.Transform(hflip=True)  # 거울모드
)
```

### GPU 인코더 설정
```python
encoder = H264Encoder(
    bitrate=5000000,               # 5Mbps
    repeat=True,                   # SPS/PPS 반복
    iperiod=30,                    # I-프레임 주기
    framerate=30                   # 30fps
)
```

## 운영 가이드

### 시작/중지
```bash
# 시스템 시작 (통합 서버)
python3 webmain.py

# 웹 접속
http://라즈베리파이IP:8001

# 시스템 종료
Ctrl+C 또는 웹 UI에서 종료
```

### 성능 지표
| 기능 | CPU | 메모리 | 대역폭 | 비고 |
|------|-----|--------|--------|------|
| 듀얼 스트리밍 (480p) | ~10% | 50MB | ~2Mbps | MJPEG |
| 듀얼 스트리밍 (720p) | ~15% | 70MB | ~4Mbps | MJPEG |
| 듀얼 녹화 (720p) | ~12% | 60MB | 5Mbps/카메라 | H.264 |
| **전체 시스템** | **~25%** | **120MB** | **~14Mbps** | 모든 기능 |

### 문제 해결

#### 카메라 연결 확인
```bash
rpicam-hello --list-cameras
python3 -c "from picamera2 import Picamera2; print('OK')"
```

#### 성능 최적화
```bash
# GPU 메모리 확인/설정 (256MB 권장)
vcgencmd get_mem gpu
sudo raspi-config > Advanced Options > Memory Split

# 디스크 공간 확인
df -h videos/

# 프로세스 상태 확인
ps aux | grep python3
```

## 개발 정보

### 주요 아키텍처 개선
#### 2025-09-23 (통합 시스템)
1. **카메라 인스턴스 재사용**: 중복 생성 방지, 안정성 향상
2. **독립적 녹화 시스템**: 웹 접속과 무관한 24시간 연속 녹화
3. **리소스 분리**: 스트리밍(lores) vs 녹화(main) 스트림 분리
4. **오류 복구**: 웹 클라이언트 접속 시 녹화 중단 문제 해결

#### 2025-09-23 (JSON 설정 시스템)
1. **설정 중앙화**: 모든 하드코딩 값을 config.json으로 이동
2. **ConfigManager 구현**: 설정 관리 전용 클래스 도입
3. **유연한 설정**: 세그먼트 길이, 비트레이트 등 운영 중 변경 가능
4. **기본값 제공**: 설정 누락 시 안전한 기본값 자동 적용

### 코딩 가이드라인
- **Python**: PEP 8 준수
- **비동기**: FastAPI async/await 활용
- **로깅**: 상세한 디버그 정보 포함
- **오류 처리**: 복구 가능한 예외 처리

### 의존성
```bash
# 시스템 패키지
sudo apt install python3-picamera2 python3-libcamera ffmpeg

# Python 패키지
pip3 install fastapi uvicorn opencv-python numpy psutil
```

---

**마지막 업데이트**: 2025-09-23 (JSON 설정 시스템 추가)