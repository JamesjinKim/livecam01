# SHT 듀얼 LIVE 카메라 시스템

라즈베리파이 5 기반 듀얼 카메라 CCTV 스트리밍 시스템입니다. 실시간 스트리밍과 자동 녹화 기능을 제공하며, 거울모드를 지원합니다.

## 🎯 주요 기능

- **듀얼 카메라 실시간 스트리밍** - 두 개의 카메라 동시 MJPEG 스트리밍
- **다중 뷰 모드** - 듀얼 뷰 / 싱글 뷰 즉시 전환
- **거울모드 지원** - 좌우 반전 모드 (hflip)
- **다중 클라이언트** - 최대 2명 동시 접속 지원
- **자동 녹화** - 30초 단위 연속 녹화 (24시간)
- **실시간 모니터링** - 하트비트 기반 상태 표시
- **반응형 웹 UI** - 모바일/데스크톱 지원

## 🏗️ 시스템 구성

### 하드웨어 요구사항
- **Raspberry Pi 5** (BCM2712)
- **OV5647 카메라 모듈** × 2개
- **MicroSD 카드** 32GB 이상
- **GPU 메모리** 256MB 권장

### 소프트웨어 스택
- **백엔드**: FastAPI + Picamera2 + OpenCV
- **프론트엔드**: Vanilla JavaScript + CSS
- **스트리밍**: MJPEG over HTTP
- **영상처리**: VideoCore VII GPU 가속

## 📁 프로젝트 구조

```
livecam1/
├── webmain.py              # 메인 CCTV 서버
├── config.yaml             # 시스템 설정
├── requirements.txt        # Python 의존성
├── web/                    # 웹 인터페이스
│   ├── api.py             # FastAPI 라우터
│   └── static/
│       ├── index.html     # 메인 페이지
│       ├── style.css      # 스타일시트
│       └── script.js      # JavaScript
├── videos/                 # 녹화 파일 저장소
│   └── cam_rec/           # 30초 단위 녹화
│       ├── cam0/
│       └── cam1/
├── README.md              # 사용자 가이드 (현재 파일)
└── CLAUDE.md              # 개발자 기술 문서
```

## 🚀 설치 및 실행

### 1. 시스템 패키지 설치
```bash
# 필수 시스템 패키지
sudo apt update
sudo apt install -y python3-picamera2 python3-libcamera ffmpeg

# GPU 메모리 설정 (권장)
sudo raspi-config
# Advanced Options > Memory Split > 256
```

### 2. Python 패키지 설치
```bash
pip3 install -r requirements.txt
```

### 3. 카메라 연결 확인
```bash
# 카메라 감지 확인
rpicam-hello --list-cameras

# 출력 예시:
# 0 : ov5647 [2592x1944] (/base/axi/pcie@1000120000/rp1/i2c@88000/ov5647@36)
# 1 : ov5647 [2592x1944] (/base/axi/pcie@1000120000/rp1/i2c@80000/ov5647@36)
```

### 4. 서버 실행
```bash
# CCTV 스트리밍 서버 시작
python3 webmain.py
```

### 5. 웹 접속
브라우저에서 `http://라즈베리파이IP:8001` 접속

## ⚙️ 설정

### config.yaml 주요 설정

```yaml
camera:
  default_resolution: "640x480"  # 기본 해상도
  fps: 30                        # 프레임률
  mirror_mode: true              # 거울모드 활성화

stream:
  max_clients_480p: 2            # 480p 최대 클라이언트
  jpeg_quality: 85               # JPEG 품질

recording:
  segment_duration: 30           # 녹화 세그먼트 (초)
  auto_recording: true           # 자동 녹화 활성화

system:
  host: "0.0.0.0"               # 서버 호스트
  port: 8001                     # 서버 포트
```

## 🎮 사용법

### 웹 인터페이스
1. **듀얼 뷰**: 두 카메라 동시 보기
2. **싱글 뷰**: 카메라 0 또는 1 개별 보기
3. **해상도 변경**: 480p 지원
4. **상태 모니터링**: 실시간 FPS, 클라이언트 수, 스트림 상태

### 시스템 상태 표시기
- **LIVE** (녹색): 정상 스트리밍
- **DELAY** (노란색): 지연 발생
- **BUSY** (노란색): 클라이언트 제한
- **OFFLINE** (검은색): 서버 연결 끊김

- **REC** (주황색): 정상 작동 중
- **IDLE** (회색): 대기 상태
- **OFFLINE** (검은색): 시스템 오프라인

## 📊 성능 지표

| 모드 | 해상도 | CPU 사용률 | 메모리 | 비고 |
|------|--------|------------|--------|------|
| 듀얼 스트리밍 | 480p | ~7% | 40MB | 2명 접속 |
| 듀얼 스트리밍 | 720p | ~11% | 50MB | 2명 접속 |
| 자동 녹화 | 720p | ~8-10% | 30-40MB | 카메라당 |
| 통합 시스템 | - | ~25-30% | 120MB | 전체 기능 |

## 🔧 문제해결

### 카메라 인식 안됨
```bash
# 카메라 상태 확인
rpicam-hello --list-cameras

# 권한 확인
groups | grep video
sudo usermod -a -G video $USER
```

### 스트리밍 끊김
```bash
# GPU 메모리 확인
vcgencmd get_mem gpu

# 프로세스 확인
ps aux | grep python3
```

### 성능 최적화
- GPU 메모리를 256MB로 설정
- 불필요한 서비스 종료
- 디스크 공간 확인: `df -h`

## 🌐 API 엔드포인트

### 스트리밍
- `GET /stream/0` - 카메라 0 스트림
- `GET /stream/1` - 카메라 1 스트림
- `GET /stream` - 현재 활성 카메라 스트림

### 제어
- `POST /switch/{camera_id}` - 카메라 전환
- `POST /api/dual_mode/{enable}` - 듀얼 모드 토글
- `POST /api/resolution/{resolution}` - 해상도 변경

### 상태
- `GET /api/stats` - 시스템 통계
- `GET /api/recording/status` - 녹화 상태

## 📝 로그 및 디버깅

로그 파일 위치: 콘솔 출력
로그 레벨: `config.yaml`에서 설정 가능

```bash
# 실시간 로그 확인
python3 webmain.py

# 디버그 모드
# config.yaml에서 log_level: "DEBUG"로 설정
```

## 🔒 보안 고려사항

- 내부 네트워크에서만 사용 권장
- 필요시 역방향 프록시(nginx) 사용
- 방화벽 설정으로 포트 접근 제한

## 🤝 기여

이 프로젝트는 개인 프로젝트입니다. 버그 리포트나 개선 제안은 이슈로 등록해 주세요.

## 📄 라이선스

개인 사용 목적으로 제작된 프로젝트입니다.

---

**마지막 업데이트**: 2025-09-22
**버전**: 3.0 (영상녹화 버튼 제거, UI 최적화)
