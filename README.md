# SHT 듀얼 LIVE 카메라

라즈베리파이 5 기반 듀얼 카메라 CCTV 스트리밍 + 30초 연속 녹화 시스템

## 시스템 구성

### Part 1: 듀얼 카메라 CCTV 스트리밍
- **메인 버전**: `webmain.py` + `web/` - 듀얼 뷰 지원 웹/백엔드 분리 구조
- **듀얼 뷰**: 두 카메라(640x480 각각)를 나란히 동시 보기
- **싱글 뷰**: 카메라 0 또는 카메라 1 선택 시 해당 카메라만 크게 보기
- **실시간 전환**: 버튼 클릭으로 듀얼/싱글 뷰 즉시 전환

### Part 2: 30초 연속 녹화 시스템
- **카메라 0 녹화**: `rec_cam0.py` - 30초 단위 연속 녹화
- **카메라 1 녹화**: `rec_cam1.py` - 30초 단위 연속 녹화
- **자동 파일 관리**: 날짜별 폴더 자동 생성 및 정리

---

## 빠른 시작

### 필수 요구사항
- **하드웨어**: Raspberry Pi 5, OV5647 카메라 모듈 ×2
- **OS**: Raspberry Pi OS (64-bit)
- **Python**: 3.11+

### 설치

#### 자동 설치 (권장)
```bash
# 저장소 클론
git clone https://github.com/JamesjinKim/livecam01.git
cd livecam01

# 설치 스크립트 실행
./install.sh
```

#### 수동 설치
```bash
# 시스템 패키지 설치
sudo apt update
sudo apt install -y python3-picamera2 python3-libcamera ffmpeg python3-pip

# Python 의존성 설치
pip3 install -r requirements.txt --break-system-packages

# 사용자 권한 설정
sudo usermod -a -G video $USER
# 재로그인 필요

# GPU 메모리 설정 (권장: 256MB)
sudo raspi-config  # Advanced Options → Memory Split → 256
```

---

## Part 1: CCTV 실시간 스트리밍

### 주요 기능
- **듀얼/싱글 뷰 전환**: 실시간 카메라 뷰 모드 변경
- **다중 클라이언트**: 최대 2명 동시 접속 (안정적인 30fps)
- **동적 해상도**: 480p/720p 선택
- **실시간 통계**: FPS, 프레임 수, 데이터 크기
- **웹 인터페이스**: 브라우저 기반 제어

### 사용 방법

#### 1. CCTV 스트리밍 시작
```bash
python3 webmain.py
```

#### 2. 웹 접속
```
브라우저에서 접속: http://라즈베리파이_IP:8001
```

#### 3. 인터페이스 사용
- **뷰 모드 전환**: Dual View / Camera 0 / Camera 1 버튼 클릭
- **해상도 변경**: 480p / 720p 버튼 선택
- **상태 확인**: 실시간 통계 패널 모니터링
- **하트비트**: LIVE (정상), DELAY (지연), ERROR (오류), OFFLINE (오프라인)

#### 4. 시스템 종료
- **터미널**: `Ctrl+C` 입력 (카메라 자동 정리 후 종료)

---

## Part 2: 30초 연속 녹화 시스템

### 주요 기능
- **연속 녹화**: 24시간 30초 단위로 끊김없이 녹화
- **듀얼 카메라**: 카메라 0, 1 독립적으로 동시 녹화
- **자동 관리**: 날짜별 폴더 생성 및 파일명 타임스탬프
- **디스크 관리**: 여유 공간 모니터링 및 경고

### 사용 방법

#### 1. 녹화 시작
```bash
# 터미널 1: 카메라 0 녹화
python3 rec_cam0.py

# 터미널 2: 카메라 1 녹화
python3 rec_cam1.py
```

#### 2. 파일 저장 위치
```
videos/cam_rec/
├── cam0/
│   └── 250915/    # YYMMDD 날짜별 폴더
│       ├── cam0_20250915_143025.mp4
│       └── cam0_20250915_143055.mp4
└── cam1/
    └── 250915/
        ├── cam1_20250915_143025.mp4
        └── cam1_20250915_143055.mp4
```

#### 3. 녹화 종료
- `Ctrl+C` 입력으로 안전하게 종료
- 현재 녹화 중인 파일 자동 저장

---

## 통합 운영 가이드

### 동시 실행 권장 방법

```bash
# 터미널 1: CCTV 실시간 모니터링
python3 webmain.py

# 터미널 2: 카메라 0 연속 녹화
python3 rec_cam0.py

# 터미널 3: 카메라 1 연속 녹화
python3 rec_cam1.py
```

### 운영 팁

#### 일반 모니터링
- CCTV 스트리밍으로 실시간 확인
- 웹 브라우저로 원격 모니터링

#### 24시간 녹화
- 30초 단위 연속 녹화로 블랙박스 기능
- 날짜별 자동 분류로 쉬운 검색

#### 리소스 관리
- CCTV + 듀얼 녹화 동시 실행 시 CPU ~25-30% 사용
- 라즈베리파이 5의 충분한 성능으로 안정적 운영

---

## 문제 해결

### 카메라 인식 오류
```bash
# 카메라 연결 확인
rpicam-hello --list-cameras

# Picamera2 라이브러리 확인
python3 -c "from picamera2 import Picamera2; print('Picamera2 OK')"

# GPU 메모리 할당 확인 (256MB 권장)
vcgencmd get_mem gpu

# 권한 확인
groups | grep video
```

### 스트리밍 끊김
- 네트워크 대역폭 확인
- 다른 클라이언트 연결 수 확인
- 해상도를 480p로 낮춰서 테스트

### 녹화 실패
- 디스크 공간 확인: `df -h`
- 카메라 사용 중인 다른 프로세스 확인
- 파일 권한 확인

---

## 고급 설정

### systemd 자동 시작 설정

#### CCTV 서비스
```bash
# /etc/systemd/system/cctv.service
[Unit]
Description=CCTV Streaming System
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/livecam1
ExecStart=/usr/bin/python3 webmain.py
Restart=always

[Install]
WantedBy=multi-user.target
```

#### 녹화 서비스
```bash
# /etc/systemd/system/recording.service
[Unit]
Description=Camera Recording System
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/livecam1
ExecStart=/bin/bash -c "python3 rec_cam0.py & python3 rec_cam1.py"
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 활성화 및 시작
sudo systemctl enable cctv.service recording.service
sudo systemctl start cctv.service recording.service
```

### 성능 최적화
```bash
# GPU 메모리 할당 증가
sudo raspi-config
# Advanced Options → Memory Split → 256

# CPU 거버너 설정
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

---

## 시스템 사양

### 성능 지표
| 기능 | CPU 사용률 | 메모리 | 비고 |
|------|------------|--------|------|
| CCTV (480p) | ~7% | 40MB | 듀얼 뷰 |
| CCTV (720p) | ~11% | 50MB | 듀얼 뷰 |
| 녹화 (720p) | ~8-10% | 30-40MB | 카메라당 |
| 전체 시스템 | ~25-30% | 120MB | 모든 기능 동시 |

### 저장 용량
- 30초 영상 (720p): ~6-8MB
- 시간당: ~720-960MB
- 일일 (24시간): ~17-23GB

---

## 라이선스 및 기여

### 문서 참조
- **PRD.md**: 상세 기술 명세 및 요구사항
- **CLAUDE.md**: 개발자 기술 문서

### 버전 정보
- **v3.1**: 듀얼 뷰 CCTV + 30초 연속 녹화 통합 시스템
- **마지막 업데이트**: 2025-09-15