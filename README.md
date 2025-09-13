# 🎥 SHT 듀얼 LIVE 카메라

라즈베리파이 5 기반 **듀얼 LIVE 카메라 동시 뷰** CCTV 스트리밍 블랙박스 시스템

## 📋 시스템 구성

### 🔴 Part 1: 듀얼 카메라 CCTV 스트리밍 🎆
- **메인 버전**: `webmain.py` + `web/` - **듀얼 뷰 지원** 웹/백엔드 분리 구조
- **듀얼 뷰**: 두 카메라(640x480 각각)를 나란히 동시 보기
- **싱글 뷰**: 카메라 0 또는 카메라 1 선택 시 해당 카메라만 크게 보기
- **실시간 전환**: 버튼 클릭으로 듀얼/싱글 뷰 즉시 전환
- **레거시 버전**: `picam2_main.py` - 기존 통합 CCTV (토글 방식)

### ⚫ Part 2: 모션 감지 블랙박스 (detection_cam0.py, detection_cam1.py)
OpenCV 기반 지능형 모션 감지 및 이벤트 녹화 시스템

---

## 🚀 빠른 시작

### 필수 요구사항
- **하드웨어**: Raspberry Pi 5, OV5647 카메라 모듈 ×2
- **OS**: Raspberry Pi OS (64-bit)
- **Python**: 3.11+

### 설치

#### 🚀 자동 설치 (권장)
```bash
# 저장소 클론
git clone https://github.com/JamesjinKim/livecam1.git
cd livecam1

#### 🔧 수동 설치
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

## 🔴 Part 1: CCTV 실시간 스트리밍

### ✨ 주요 기능
- 🎯 **단일 클라이언트 제한**: 안정적인 30fps 스트리밍
- 🔄 **듀얼 카메라 토글**: 실시간 카메라 전환 (< 3초)
- 📺 **동적 해상도**: 480p/720p 선택
- 📊 **실시간 통계**: FPS, 프레임 수, 데이터 크기
- 🌐 **웹 인터페이스**: 브라우저 기반 제어

### 🎮 사용 방법

#### 1. CCTV 스트리밍 시작

**🔧 웹 분리 버전 (코드 보호용)** ⭐ 신규:
```bash
python3 webmain.py
```

#### 2. 웹 접속
```
브라우저에서 접속: http://라즈베리파이_IP:8001
```

> **💡 참고**: 두 버전 모두 동일한 기능과 성능을 제공합니다. 웹 분리 버전은 향후 코드 보호(Cython 컴파일)를 위한 구조입니다.

#### 3. 인터페이스 사용
- **카메라 전환**: Camera 0 ↔ Camera 1 버튼 클릭
- **해상도 변경**: 480p / 720p 버튼 선택
- **상태 확인**: 실시간 통계 패널 모니터링
- **하트비트**: LIVE (정상), DELAY (지연), OFFLINE (오프라인) 상태 표시

#### 4. 시스템 종료
- **웹 인터페이스**: 브라우저에서 `/exit` 페이지 접속 후 종료 버튼 클릭
- **터미널**: `Ctrl+C` 입력 (카메라 자동 정리 후 종료)

### ⚙️ 설정 최적화

#### 성능 튜닝

#### 네트워크 최적화
- **내부 네트워크**: 최상의 성능
- **WiFi**: 480p 권장
- **유선 연결**: 720p 고품질

### 🔧 문제 해결

#### 카메라 인식 오류
```bash
# 카메라 확인
rpicam-hello --list-cameras

# 카메라 테스트
rpicam-hello --camera 0 --timeout 2000
```

#### 스트리밍 불안정
- 다른 클라이언트 연결 여부 확인
- 네트워크 대역폭 확인
- 라즈베리파이 온도 체크

#### 시스템 리소스
- **CPU 사용률**: ~10% (단일 카메라)
- **메모리**: ~50-60MB

## 🔄 통합 운영 가이드

### 동시 실행 권장 방법

#### 터미널 1: CCTV 실시간 모니터링
```bash
# 웹 분리 버전 (동일 기능)
python3 webmain.py

# → http://라즈베리파이_IP:8001 접속
### 💡 운영 팁

#### 일반 모니터링
- CCTV 스트리밍만 상시 실행
- 웹 브라우저로 실시간 확인

#### 보안 강화 모드
- 야간 또는 외출 시 모션 감지 추가 실행
- 이벤트 발생 시 자동 30초 영상 저장

#### 리소스 관리
- 두 시스템 동시 실행 시 CPU ~40-50% 사용
- 라즈베리파이 5 권장 (충분한 성능)

### Q: 카메라가 인식되지 않아요 (Picamera2 대응) ⚡
**A**: 
```bash
# 카메라 연결 확인
rpicam-hello --list-cameras

# Picamera2 라이브러리 확인
python3 -c "from picamera2 import Picamera2; print('Picamera2 OK')"

# GPU 메모리 할당 확인 (256MB 권장)
vcgencmd get_mem gpu

# 권한 확인
sudo usermod -a -G video $USER
# 재로그인 필요
```

### Q: Picamera2와 rpicam-vid 차이점이 뭐예요?
**A**: 
- **rpicam-vid** (구버전): 서브프로세스 방식, 장기 스트리밍 시 멈춤 문제
- **Picamera2** (신버전): GPU 직접 액세스, 안정성 대폭 향상, CPU 20-30% 절약 ⚡

---

## 🛠️ 고급 설정

### systemd 자동 시작 설정
```bash
# /etc/systemd/system/cctv.service
[Unit]
Description=CCTV Streaming System
After=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/livecam
ExecStart=/usr/bin/python3 webmain.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cctv.service
sudo systemctl start cctv.service
```

### 방화벽 설정
```bash
# 포트 8001 열기
sudo ufw allow 8001
```

### 성능 최적화
```bash
# GPU 메모리 할당 증가
sudo raspi-config
# Advanced Options → Memory Split → 128
```

---

🔧 라즈베리파이 부팅 시 자동 시작 구현 방법
방법 1: systemd 서비스 (권장)
Write(smart-security.service)
write to smart-security.service

 [Unit]
 Description=Smart Security System - Integrated Controller
 After=multi-user.target network.target
 Wants=network.target
 
 [Service]
 Type=simple
 User=shinho
 Group=shinho
 WorkingDirectory=/home/shinho/shinho/livecam
 ExecStart=/usr/bin/python3 
/home/shinho/shinho/livecam/webmain.py
 Restart=always
 RestartSec=10
 
 # 환경 변수 설정
 Environment=HOME=/home/shinho
 Environment=USER=shinho
 
 # 로그 설정
 StandardOutput=journal
 StandardError=journal
 SyslogIdentifier=smart-security
 
 [Install]
 WantedBy=multi-user.target


### 문서 참조 (2025.09 업데이트)
- **PRD.md**: 상세 기술 명세 (Picamera2 버전 2.0 반영)
- **CLAUDE.md**: 개발자 기술 문서 (Picamera2 마이그레이션 상세 정보)
- **로그 분석**: 콘솔 출력 + PiSP 하드웨어 로그 디버깅

### 일반적인 문제 (Picamera2 기반)
1. **스트리밍 끊김**: 네트워크 확인 / Picamera2 인스턴스 충돌
2. **모션 오감지**: 민감도 조정
3. **저장 실패**: 디스크 공간 확인
4. **카메라 오류**: 하드웨어 연결 / GPU 메모리 설정 (256MB) 점검
5. **"Pipeline handler in use" 에러**: 다른 카메라 어플리케이션 종료 필요

### 버전 정보
- **v1.0**: 초기 듀얼 카메라 CCTV + 모션 감지 시스템 (rpicam-vid 방식)
- ⚡ **v2.0**: Picamera2 기반 GPU 직접 액세스 마이그레이션 (2025-09-09)
- **마지막 업데이트**: 2025-09-09 (Picamera2 완전 대체)
- **호환성**: Raspberry Pi 5, Python 3.11+, Picamera2 0.3.12+