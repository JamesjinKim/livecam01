# SHT 듀얼 LIVE 카메라

라즈베리파이 5 기반 듀얼 카메라 CCTV 스트리밍 + 30초 연속 녹화 시스템

## 주요 기능

### CCTV 실시간 스트리밍
- **듀얼/싱글 뷰**: 두 카메라 동시 보기 또는 개별 카메라 선택
- **거울모드**: 좌우 반전 지원으로 자연스러운 화면
- **다중 접속**: 최대 2명 동시 접속 (480p/720p)
- **실시간 모니터링**: 웹 브라우저 기반 원격 접속
- **하트비트**: LIVE/DELAY/ERROR 상태 실시간 표시

### 30초 연속 녹화
- **24시간 녹화**: 카메라 0, 1 독립적 30초 단위 연속 녹화
- **자동 관리**: 날짜별 폴더 생성 및 타임스탬프 파일명
- **안정적 저장**: 끊김없는 연속 녹화로 블랙박스 기능

## 빠른 시작

### 필수 요구사항
- **하드웨어**: Raspberry Pi 5, OV5647 카메라 모듈 ×2
- **OS**: Raspberry Pi OS (64-bit)
- **Python**: 3.11+

### 설치
```bash
# 시스템 패키지 설치
sudo apt update
sudo apt install -y python3-picamera2 python3-libcamera ffmpeg python3-pip

# Python 의존성 설치
pip3 install fastapi uvicorn picamera2 opencv-python numpy psutil --break-system-packages

# 사용자 권한 설정
sudo usermod -a -G video $USER
# 재로그인 필요

# GPU 메모리 설정 (권장: 256MB)
sudo raspi-config  # Advanced Options → Memory Split → 256
```

## 사용 방법

### 1. CCTV 스트리밍 시작
```bash
python3 webmain.py
```

### 2. 웹 접속
```
브라우저에서 접속: http://라즈베리파이_IP:8001
```

### 3. 30초 연속 녹화 (선택사항)
```bash
# 터미널 1: 카메라 0 녹화
python3 rec_cam0.py

# 터미널 2: 카메라 1 녹화
python3 rec_cam1.py
```

### 4. 웹 인터페이스 사용
- **뷰 모드**: Dual View / Camera 0 / Camera 1 버튼으로 전환
- **해상도**: 480p / 720p 선택
- **상태 확인**: 실시간 통계 및 하트비트 모니터링

## 파일 저장 위치
```
videos/cam_rec/
├── cam0/
│   └── 250916/    # YYMMDD 날짜별 폴더
│       ├── cam0_20250916_143025.mp4
│       └── cam0_20250916_143055.mp4
└── cam1/
    └── 250916/
        ├── cam1_20250916_143025.mp4
        └── cam1_20250916_143055.mp4
```

## 성능 지표
| 기능 | CPU 사용률 | 메모리 | 비고 |
|------|------------|--------|------|
| CCTV (480p) | ~7% | 40MB | 듀얼 뷰 |
| CCTV (720p) | ~11% | 50MB | 듀얼 뷰 |
| 녹화 (720p) | ~8-10% | 30-40MB | 카메라당 |
| 전체 시스템 | ~25-30% | 120MB | 모든 기능 |

## 문제 해결

### 카메라 인식 오류
```bash
# 카메라 연결 확인
rpicam-hello --list-cameras

# Picamera2 라이브러리 확인
python3 -c "from picamera2 import Picamera2; print('OK')"

# 권한 확인
groups | grep video
```

### 스트리밍 문제
- 네트워크 대역폭 확인
- 해상도를 480p로 낮춰서 테스트
- GPU 메모리 할당 확인: `vcgencmd get_mem gpu`

### 녹화 문제
- 디스크 공간 확인: `df -h`
- 카메라 사용 중인 프로세스 확인: `ps aux | grep python3`

## 고급 설정

### systemd 자동 시작
```bash
# /etc/systemd/system/cctv.service
[Unit]
Description=CCTV Streaming System
After=multi-user.target

[Service]
Type=simple
User=shinho
WorkingDirectory=/home/shinho/shinho/livecam1
ExecStart=/usr/bin/python3 webmain.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 활성화
sudo systemctl enable cctv.service
sudo systemctl start cctv.service
```

---

**마지막 업데이트**: 2025-09-16 (거울모드 추가)