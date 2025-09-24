# 🎥 SHT 듀얼 LIVE 카메라

**라즈베리파이 5 기반 듀얼 카메라 CCTV 시스템**
실시간 웹 스트리밍 + 24시간 자동 녹화

---

## ✨ 주요 기능

### 📺 실시간 웹 스트리밍
- **듀얼/싱글 뷰**: 두 카메라 동시 보기 또는 개별 선택
- **거울모드**: 좌우 반전으로 자연스러운 화면
- **다중 접속**: 최대 2명 동시 접속 지원
- **해상도 선택**: 480p (2Mbps) / 720p (4Mbps)
- **실시간 모니터링**: LIVE/OFFLINE 상태 + FPS/통계

### 🎬 24시간 자동 녹화
- **연속 녹화**: 30초 단위 끊김없는 24시간 녹화
- **듀얼 카메라**: 두 카메라 독립적 동시 녹화
- **GPU 가속**: H.264 하드웨어 인코딩 (5Mbps)
- **자동 관리**: 타임스탬프 파일명, 실시간 저장

---

## 🚀 빠른 시작

### 📋 필수 요구사항
- **하드웨어**: Raspberry Pi 5 + OV5647 카메라 ×2
- **OS**: Raspberry Pi OS (64-bit)
- **Python**: 3.11+

### ⚙️ 설치
```bash
# 1. 시스템 패키지 설치
sudo apt update
sudo apt install -y python3-picamera2 python3-libcamera ffmpeg

# 2. Python 패키지 설치
pip3 install fastapi uvicorn opencv-python numpy psutil

# 3. 사용자 권한 설정
sudo usermod -a -G video $USER
# 재로그인 필요

# 4. GPU 메모리 설정 (권장: 256MB)
sudo raspi-config  # Advanced Options → Memory Split → 256
```

---

## 📖 사용 방법

### 1️⃣ 시스템 시작
```bash
python3 webmain.py
```

### 2️⃣ 웹 접속
```
브라우저에서: http://라즈베리파이IP:8001
```

### 3️⃣ 웹 인터페이스 사용
- **🔄 뷰 전환**: `Dual View` / `Camera 0` / `Camera 1` 버튼
- **📐 해상도**: `480p` / `720p` 선택
- **📊 모니터링**: 실시간 FPS, 프레임 수, 연결 상태 확인

### 4️⃣ 시스템 종료
- **방법 1**: `Ctrl+C` (터미널)
- **방법 2**: 웹 UI 종료 버튼

---

## 📁 녹화 파일 저장

### 저장 위치
```
videos/
├── cam0/              # 카메라 0 녹화 파일
│   ├── cam0_20250923_143025.mp4
│   ├── cam0_20250923_143055.mp4
│   └── cam0_20250923_143125.mp4
└── cam1/              # 카메라 1 녹화 파일
    ├── cam1_20250923_143025.mp4
    ├── cam1_20250923_143055.mp4
    └── cam1_20250923_143125.mp4
```

### 파일 규칙
- **형식**: `cam{카메라번호}_{YYYYMMDD}_{HHMMSS}.mp4`
- **길이**: 30초 (자동 분할)
- **인코딩**: H.264, 5Mbps, 30fps
- **크기**: 약 20MB/파일 (720p 기준)

---

## 📊 성능 정보

### 시스템 리소스 (Ra스베리파이 5 기준)
| 기능 | CPU | 메모리 | 대역폭 | 파일 크기 |
|------|-----|--------|--------|-----------|
| 듀얼 스트리밍 (480p) | ~10% | 50MB | ~2Mbps | - |
| 듀얼 스트리밍 (720p) | ~15% | 70MB | ~4Mbps | - |
| 듀얼 녹화 (720p) | ~12% | 60MB | 5Mbps/카메라 | 20MB/30초 |
| **전체 시스템** | **~25%** | **120MB** | **~14Mbps** | **2.8GB/시간** |

---

## 🔧 문제 해결

### ❌ 카메라 인식 오류
```bash
# 카메라 연결 확인
rpicam-hello --list-cameras

# 라이브러리 확인
python3 -c "from picamera2 import Picamera2; print('OK')"

# 권한 확인
groups | grep video
```

### 🌐 스트리밍 문제
- 네트워크 대역폭 확인
- 해상도를 480p로 낮춰서 테스트
- 다른 기기에서 접속 테스트

### 💾 녹화 문제
```bash
# 디스크 공간 확인
df -h

# 실행 중인 프로세스 확인
ps aux | grep python3

# GPU 메모리 확인
vcgencmd get_mem gpu
```

### 🔌 포트 충돌
```bash
# 8001 포트 사용 중인 프로세스 확인
sudo lsof -i :8001

# 기존 프로세스 종료
sudo pkill -f webmain.py
```

---

## ⚡ 고급 설정

### 🔄 자동 시작 설정 (systemd)
```bash
# 서비스 파일 생성
sudo nano /etc/systemd/system/cctv.service
```

```ini
[Unit]
Description=SHT CCTV Streaming System
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/livecam
ExecStart=/usr/bin/python3 webmain.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 활성화 및 시작
sudo systemctl enable cctv.service
sudo systemctl start cctv.service

# 상태 확인
sudo systemctl status cctv.service
```

### 🔍 로그 확인
```bash
# 실시간 로그 보기
sudo journalctl -u cctv.service -f

# 최근 로그 확인
sudo journalctl -u cctv.service --since "1 hour ago"
```

---

## 🛠️ 기술 사양

- **프레임워크**: FastAPI + Picamera2
- **스트리밍**: MJPEG (lores 스트림)
- **녹화**: H.264 GPU 인코딩 (main 스트림)
- **웹 UI**: Vanilla JavaScript + 반응형 CSS
- **포트**: 8001 (HTTP)

---

## 📞 지원

문제가 발생하면 다음을 확인하세요:
1. 카메라 연결 상태
2. 네트워크 연결
3. GPU 메모리 설정 (256MB)
4. 디스크 여유 공간
5. 시스템 로그

---

**마지막 업데이트**: 2025-09-23 (통합 시스템 완성)