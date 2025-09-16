# CLAUDE.md - 개발자 기술 문서

## 프로젝트 개요

**SHT 듀얼 LIVE 카메라** - 라즈베리파이 5 기반 듀얼 카메라 CCTV 스트리밍 시스템
- **목적**: 실시간 CCTV 스트리밍 + 거울모드 지원
- **핵심**: FastAPI 웹 서버 + Picamera2 GPU 가속 인코딩
- **특징**: 다중 클라이언트 지원 (최대 2명), 듀얼/싱글 뷰 전환

## 시스템 아키텍처

### 기술 스택
- **하드웨어**: Raspberry Pi 5 (BCM2712), OV5647 카메라 모듈 × 2
- **CCTV**: FastAPI + MJPEG 스트리밍 (최대 2명 동시 접속)
- **영상 처리**: Picamera2 라이브러리 + VideoCore VII GPU 직접 액세스
- **프론트엔드**: Vanilla JavaScript, 반응형 웹 UI + 실시간 하트비트 모니터링

### 현재 파일 구조
```
livecam1/
├── webmain.py             # 메인 CCTV 서버 (Picamera2 기반)
├── web/                   # 웹 관련 파일
│   ├── static/
│   │   ├── index.html     # 듀얼 뷰 메인 페이지
│   │   ├── style.css      # 듀얼 뷰 스타일시트
│   │   └── script.js      # 듀얼 뷰 JavaScript
│   └── api.py             # FastAPI 라우터
├── README.md              # 사용자 가이드
├── CLAUDE.md              # 개발자 기술 문서 (현재 파일)
└── videos/                # 영상 저장소
    └── cam_rec/           # 30초 단위 녹화 파일
        ├── cam0/
        └── cam1/
```

## 핵심 기능

### 1. 듀얼 카메라 CCTV 스트리밍
- **실시간 스트리밍**: MJPEG 방식으로 30fps 보장
- **듀얼/싱글 뷰**: 버튼 클릭으로 즉시 전환
- **거울모드**: 좌우 반전 지원 (`libcamera.Transform(hflip=True)`)
- **다중 클라이언트**: 해상도별 최대 2명 동시 접속
- **동적 해상도**: 480p/720p 선택

### 2. 웹 인터페이스
- **하트비트 모니터링**: LIVE/DELAY/ERROR/OFFLINE 상태 표시
- **실시간 통계**: FPS, 프레임 수, 데이터 크기
- **반응형 UI**: 모바일/데스크톱 지원
- **직관적 컨트롤**: 카메라 전환, 해상도 변경

### 3. 30초 연속 녹화 시스템
- **연속 녹화**: 24시간 30초 단위 끊김없이 녹화
- **듀얼 카메라**: 카메라 0, 1 독립적 동시 녹화
- **자동 관리**: 날짜별 폴더 생성 및 파일명 타임스탬프

## 개발 가이드

### 코딩 컨벤션
- **Python**: PEP 8 준수
- **함수명**: snake_case
- **클래스명**: PascalCase
- **상수**: UPPER_CASE
- **주석**: 한국어 + 영어 혼용

### 중요 설정

#### 카메라 설정 (거울모드 포함)
```python
config = picam2.create_video_configuration(
    main={
        "size": (width, height),
        "format": "RGB888" if camera_id == 0 else "YUV420"
    },
    buffer_count=2,
    queue=False,
    transform=libcamera.Transform(hflip=True)  # 거울모드
)
```

#### 성능 최적화
- **GPU 메모리**: 256MB 권장 (`sudo raspi-config`)
- **리소스 분산**: 카메라별 다른 포맷 사용
- **버퍼 최적화**: buffer_count=2로 레이턴시 최소화

## 운영 가이드

### 시작 방법
```bash
# CCTV 스트리밍
python3 webmain.py

# 연속 녹화 (별도 터미널)
python3 rec_cam0.py
python3 rec_cam1.py
```

### 성능 지표
| 기능 | CPU 사용률 | 메모리 | 비고 |
|------|------------|--------|------|
| CCTV (480p) | ~7% | 40MB | 듀얼 뷰 |
| CCTV (720p) | ~11% | 50MB | 듀얼 뷰 |
| 녹화 (720p) | ~8-10% | 30-40MB | 카메라당 |
| 전체 시스템 | ~25-30% | 120MB | 모든 기능 |

### 문제 해결

#### 카메라 문제
```bash
# 카메라 연결 확인
rpicam-hello --list-cameras

# Picamera2 라이브러리 확인
python3 -c "from picamera2 import Picamera2; print('OK')"

# 권한 확인
groups | grep video
```

#### 성능 문제
- GPU 메모리 부족: `vcgencmd get_mem gpu`
- 디스크 공간 확인: `df -h`
- 프로세스 충돌: `ps aux | grep python3`

## 의존성

### 시스템 패키지
```bash
sudo apt install -y python3-picamera2 python3-libcamera ffmpeg
```

### Python 패키지
```python
fastapi>=0.104.0
uvicorn>=0.24.0
picamera2>=0.3.12
opencv-python>=4.8.0
numpy>=1.24.0
psutil>=5.9.0
```

---

**마지막 업데이트**: 2025-09-16 (거울모드 추가)