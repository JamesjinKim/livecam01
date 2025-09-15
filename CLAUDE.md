# CLAUDE.md - 개발자 기술 문서

## 🎯 프로젝트 개요

**SHT 듀얼 LIVE 카메라** - 라즈베리파이 5 기반 통합 CCTV 및 모션 감지 블랙박스 시스템
- **목적**: 실시간 CCTV 스트리밍 + 지능형 모션 감지 블랙박스
- **핵심**: FastAPI 웹 서버 + OpenCV 모션 감지 + Picamera2 GPU 가속 인코딩 ⚡
- **특징**: 다중 클라이언트 CCTV (최대 2명), 프리버퍼 블랙박스, 날짜별 자동 분류
- **2025년 9월**: **rpicam-vid → Picamera2 마이그레이션 완료** (안정성 대폭 향상)

## 🏗️ 시스템 아키텍처

### 기술 스택
- **하드웨어**: Raspberry Pi 5 (BCM2712), OV5647 카메라 모듈 × 2
- **CCTV**: FastAPI + MJPEG 스트리밍 (최대 2명 동시 접속)
- **모션 감지**: OpenCV BackgroundSubtractorMOG2
- **영상 처리**: ⚡ **Picamera2 라이브러리 + VideoCore VII GPU 직접 액세스** (2025.09 업그레이드)
- **프론트엔드**: Vanilla JavaScript, 반응형 웹 UI + 실시간 하트비트 모니터링

### 시스템 구성

```
livecam/
├── webmain.py             # 🔴 메인 CCTV 서버 (Picamera2 기반) ⚡ 현재 운영중
├── cctv_main.py               # 🔴 구버전 
감지 블랙박스  
├── detection_cam0.py           # ⚫ 카메라 0 모션 
├── detection_cam1.py           # ⚫ 카메라 1 모션 감지 블랙박스
├── rec_cam0.py                 # 🧪 카메라 0 녹화 30초 기능
├── rec_cam1.py                 # 🧪 카메라 1 녹화 30초 기능
├── PRD.md                      # 📋 제품 요구사항 문서
├── README.md                   # 📖 사용자 가이드
├── CLAUDE.md                   # 🔧 개발자 기술 문서 (현재 파일)
└── videos/                     # 영상 저장소
    └── cam_rec/                # 영상 30초 단위 저장
        ├── cam0/
        │   ├── 250908/         # YYMMDD 날짜별 폴더
        │   └── 250909/
        └── cam1/
            ├── 250908/
            └── 250909/

    └── motion_events/          # 모션 감지 이벤트 저장
        ├── cam0/
        │   ├── 250908/         # YYMMDD 날짜별 폴더
        │   └── 250909/
        └── cam1/
            ├── 250908/
            └── 250909/
```

---
## Python code 내에서 이모지 사용 금지!

## 🔴 Part 1: CCTV 실시간 스트리밍 시스템

### 🚀 2025년 9월 Picamera2 마이그레이션 완료

**마이그레이션 배경**:
- rpicam-vid 서브프로세스 방식의 장기 스트리밍 중 멈춤 현상 해결
- "Pipeline handler in use by another process" 에러 근본 해결
- Pi5 VideoCore VII GPU 직접 액세스로 성능 향상

**현재 운영 중인 시스템** (2025.09.11 기준):
- ✅ **webmain.py**: 웹 듀얼 live camera 버전

**주요 개선사항**:
- ✅ 서브프로세스 → 직접 라이브러리 호출로 안정성 대폭 향상
- ✅ 기존 cctv_main.py UI/UX 100% 보존
- ✅ 하트비트 모니터링 시스템 완전 통합
- ✅ Pi5 PiSP BCM2712_D0 하드웨어 가속 활용
- ✅ **웹/백엔드 분리 구조 지원** (2025.09.11 추가)

### 📅 2025년 9월 13일 듀얼 뷰 시스템 완성 🎉

**듀얼 카메라 동시 뷰 시스템 (2025.09.13)**:
- ✅ **듀얼 뷰**: 두 카메라(640x480 각각)를 나란히 동시 표시
- ✅ **싱글 뷰**: 카메라 0 또는 카메라 1 선택 시 해당 카메라만 크게 표시
- ✅ **실시간 전환**: 버튼 클릭으로 즉시 뷰 모드 전환
- ✅ **카메라 라벨**: 모든 뷰에서 카메라 구분 라벨 표시
- ✅ **하트비트 시스템**: 듀얼/싱글 모드 자동 감지 및 상태 표시
- ✅ **그린 톤 UI**: 버튼 호버 시 그린 색상으로 통일

**백엔드 API 확장 (2025.09.13)**:
- ✅ **개별 카메라 스트림**: `/stream/0`, `/stream/1` 엔드포인트 추가
- ✅ **듀얼 모드 API**: `/api/dual_mode/{enable}` 토글 기능
- ✅ **카메라 전환 API**: `/switch/{camera_id}` 싱글 모드 전환
- ✅ **동적 스트림 관리**: 뷰 모드에 따른 카메라 인스턴스 자동 관리

**프론트엔드 완전 개편 (2025.09.13)**:
- ✅ **HTML 구조 개선**: 듀얼/싱글 뷰 컨테이너 분리
- ✅ **CSS 반응형 레이아웃**: 640x480 고정 크기로 최적화
- ✅ **JavaScript 안전성**: null 참조 방지 및 오류 처리 강화
- ✅ **실시간 UI 업데이트**: API 응답 전 즉시 UI 변경으로 반응성 향상

### 📅 2025년 9월 11일 최신 업데이트 ⭐

**웹 UI 개선 (2025.09.11)**:
- ✅ **일관된 레이아웃**: 카메라, 해상도, 시스템 상태 버튼 대칭 정렬
- ✅ **직관적 디자인**: 모든 컨트롤 요소 가로 정렬 및 동일한 간격
- ✅ **시스템 제어 → 시스템 상태**: 종료 버튼 숨김 및 상태 중심 디자인
- ✅ **하트비트 배치**: 다른 버튼과 동일한 크기와 스타일

**시스템 안정성 개선 (2025.09.11)**:
- ✅ **프레임 카운터 자동 리셋**: 10만 프레임마다 메모리 안정성을 위한 자동 초기화
- ✅ **Ctrl+C 즉시 종료**: uvicorn 시그널 핸들링 우회로 즉시 종료
- ✅ **카메라 정리 프로세스**: 종료 시 자동 리소스 정리 및 안전 종료

**웹/백엔드 분리 구조 (2025.09.11)**:
- ✅ **백엔드 로직 분리**: `CameraManager` 클래스로 핵심 카메라 제어 로직 독립
- ✅ **웹 인터페이스 분리**: `web/` 폴더로 HTML/CSS/JS 완전 분리
- ✅ **API 라우터 분리**: `web/api.py`로 FastAPI 엔드포인트 모듈화
- ✅ **코드 보호 준비**: 핵심 로직만 Cython 컴파일 가능한 구조

**현재 파일 구조 (2025.09.13)**:
```
livecam/
├── picam2_webmain.py       # 듀얼 뷰 지원 분리 버전 ⭐ 메인
├── web/                    # 웹 관련 파일
│   ├── static/
│   │   ├── index.html      # 듀얼 뷰 메인 페이지 (v2.5)
│   │   ├── exit.html       # 종료 페이지  
│   │   ├── style.css       # 듀얼 뷰 스타일시트 (v2.4)
│   │   └── script.js       # 듀얼 뷰 JavaScript (v2.5)
│   └── api.py              # 듀얼 모드 지원 FastAPI 라우터
└── devdoc.txt              # 개선 요청사항 문서
```

### 📅 2025년 9월 10일 추가 개선사항

**다중 클라이언트 지원 (2025.09.10)**:
- ✅ 해상도별 최대 2명 동시 접속 지원
- ✅ 웹 UI에 실시간 접속자 수 표시 (예: "1/2")
- ✅ 접속 제한 초과 시 HTTP 423 상태 코드 반환

**종료 처리 개선 (2025.09.10)**:
- ✅ Graceful shutdown 구현
- ✅ 시그널 핸들러 단순화 (sys.exit 사용)
- ✅ uvicorn 종료 시 asyncio.CancelledError 정상 처리

**하트비트 안정화 (2025.09.10)**:
- ✅ HEAD 요청 제거, stats API 기반 상태 감지
- ✅ CSS 레이아웃 개선 (절대 위치 사용)
- ✅ LIVE/DELAY 깜빡임 현상 해결

### 핵심 기술 구현

#### 1. 다중 클라이언트 제한 시스템 (2025.09.10 업데이트)
# 해상도별 클라이언트 제한 설정

**장점**:
- 안정적인 30fps 스트리밍 보장 (최대 2명)
- 리소스 경합 방지
- 네트워크 대역폭 최적화
- 실시간 접속자 수 모니터링

#### 2. Picamera2 기반 MJPEG 스트리밍 ⚡
**분리 버전 (webmain.py)** ⭐:

**성능 최적화 기법** (2025.09.11 개선):
- ✅ **직접 캡처**: 버퍼링 시스템 제거로 레이턴시 최소화
- ✅ **실시간 처리**: 스레드 간 통신 오버헤드 제거  
- ✅ **메모리 효율**: 불필요한 프레임 저장소 제거
- ✅ **30fps 보장**: 원본과 100% 동일한 성능 달성

#### 3. Picamera2 카메라 관리 시스템 ⚡
**Picamera2 인스턴스 관리** ⚡:
- 서브프로세스 완전 제거로 좀비 프로세스 원천 차단
- GPU 메모리 직접 관리로 안정성 향상
- Pi5 PiSP (Image Signal Processor) BCM2712_D0 하드웨어 가속

#### 4. 실시간 통계 시스템

### 웹 인터페이스 기술

#### 하트비트 모니터링 시스템 ❤️

**UI 특징** (2025.09 업그레이드):
- 전체 화면 활용 영상 표시
- ❤️ **실시간 하트비트 인디케이터**: LIVE/DELAY/ERROR/OFFLINE 상태 표시
- 실시간 통계 업데이트 (FPS, 프레임 수, 데이터 크기)
- 연결 제한 상태 자동 감지 및 표시
- 일관된 버튼 디자인 (종료/해상도 버튼 통일)

#### CSS 디자인 시스템
- **색상 팔레트**: 그레이 톤 + 파란색 액센트
- **레이아웃**: Flexbox 기반 반응형
- **인터랙션**: 호버 효과 + 활성 상태 표시

### 성능 최적화 전략

#### 메모리 관리 (Picamera2 최적화) ⚡
- **GPU 직접 액세스**: 서브프로세스 메모리 오버헤드 제거
- **Zero-copy 스트림**: Picamera2 → BytesIO 직접 전송
- **자동 버퍼 관리**: Pi5 하드웨어 버퍼링 활용
- **메모리 누수 방지**: 인스턴스 기반 리소스 관리

#### 네트워크 최적화
- **HTTP Keep-Alive**: 연결 재사용
- **MJPEG 품질**: 80% 압축 품질
- **프레임 드롭 방지**: 버퍼 임계값 관리

---

## ⚫ Part 2: 모션 감지 블랙박스 시스템

### 아키텍처 패턴

#### 1. 단일 책임 원칙 적용
```python
# 각 기능별 독립 클래스 설계
├── MotionDetectionSystem      # 메인 조정자
├── CameraStreamManager        # 카메라 스트림 전담
├── SimpleMotionDetector       # 모션 감지 알고리즘  
├── VideoRecorder             # 프리버퍼 + 녹화 시스템
├── EventManager              # 이벤트 로깅
└── Config                    # 설정 관리
```

#### 2. 프리버퍼 시스템 설계
```python
class VideoRecorder:
    def __init__(self, pre_buffer=5, post_buffer=25):
        # skip_frames를 고려한 실제 fps 계산
        self.actual_buffer_fps = FRAMERATE // SKIP_FRAME  # 30 / 3 = 10fps
        self.frame_buffer = deque(maxlen=pre_buffer * self.actual_buffer_fps)  # 50 프레임
        
    def add_frame_to_buffer(self, frame):
        # JPEG 압축으로 메모리 효율성 확보
        _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        self.frame_buffer.append(jpeg_data)
```

**핵심 설계 원리**:
- 메모리 효율: JPEG 압축 저장
- 정확한 시간: 프레임 복제로 30fps 보장
- 순환 버퍼: 고정 메모리 사용량

**알고리즘 최적화**:
- 배경 안정화: 60프레임 학습으로 false positive 감소
- 적응형 업데이트: 느린 배경 변화 대응
- 형태학적 연산: 노이즈 제거

#### 4. 영상 병합 시스템
```python
def _merge_video_files(self, input_files, output_file):
    merge_cmd = [
        "ffmpeg",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264",      # H.264 코덱
        "-preset", "fast",      # 인코딩 속도 향상
        "-t", "30",            # 정확히 30초
        "-r", "30",            # 30fps 통일
        "-pix_fmt", "yuv420p", # 호환성 향상
        "-y", str(output_file)
    ]
```

**품질 보장 메커니즘**:
- Duration 검증: ffprobe로 실제 길이 확인
- 프레임레이트 통일: 모든 구간 30fps
- 에러 복구: 60초 타임아웃 + 재시도

### 고급 기능 구현

#### 1. 날짜별 자동 분류

#### 2. 스레드 안전성

## 개발 도구 및 디버깅

### 로깅 시스템

#### CCTV 시스템 로그

### 성능 모니터링

#### 리소스 사용량

#### 성능 벤치마크
| 시스템 | CPU 사용률 | 메모리 | 디스크 I/O | 비고 |
|--------|------------|--------|------------|------|
| **CCTV (480p)** | ~7% | 40MB | 1-2MB/s | 듀얼 뷰 |
| **CCTV (720p)** | ~11% | 50MB | 3-4MB/s | 듀얼 뷰 |
| **녹화 (720p)** | ~8-10% | 30-40MB | 6-8MB/30s | 카메라당 |
| **전체 시스템** | ~25-30% | 120MB | - | 모든 기능 |

### 문제 해결 가이드

#### 1. CCTV 스트리밍 문제
```bash
# 카메라 하드웨어 확인
rpicam-hello --list-cameras
rpicam-hello --camera 0 --timeout 2000

# Picamera2 라이브러리 확인
python3 -c "from picamera2 import Picamera2; print('Picamera2 OK')"

# 권한 문제 해결
sudo usermod -a -G video $USER

# GPU 메모리 확인
vcgencmd get_mem gpu
```

#### 2. 녹화 문제
```bash
# 카메라 사용 중인 프로세스 확인
ps aux | grep rpicam

# 디스크 공간 확인
df -h /home/shinho

# 파일 권한 확인
ls -la videos/cam_rec/
```

#### 3. 듀얼 카메라 충돌
```bash
# ISP 리소스 확인
dmesg | grep -i pisp

# 카메라 리스트 확인
rpicam-hello --list-cameras
```

#### 4. 메모리 부족 문제
```bash
# GPU 메모리 증가
sudo raspi-config
# Advanced Options → Memory Split → 256

# 시스템 메모리 확인
free -h
```

---

## 배포 및 운영

### systemd 서비스 설정
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
# /etc/systemd/system/recording.service
[Unit]
Description=Camera Recording System
After=multi-user.target

[Service]
Type=simple
User=shinho
WorkingDirectory=/home/shinho/shinho/livecam1
ExecStart=/bin/bash -c "python3 rec_cam0.py & python3 rec_cam1.py"
Restart=always

[Install]
WantedBy=multi-user.target
```

## 향후 개발 계획

### 단기 개선사항
- 모바일 반응형 UI 개선
- 영상 썸네일 생성
- 디스크 공간 자동 관리

### 중기 개발
- 모션 감지 기반 이벤트 녹화
- 클라우드 백업 연동
- REST API 확장

### 장기 비전
- AI 기반 객체 감지
- 다중 라즈베리파이 클러스터
- 중앙 관제 시스템

---

## 참고 자료 및 의존성

### 외부 라이브러리
```python
# requirements.txt
fastapi>=0.104.0
uvicorn>=0.24.0
picamera2>=0.3.12
opencv-python>=4.8.0
numpy>=1.24.0
pillow>=10.0.0
psutil>=5.9.0
```

### 시스템 패키지
```bash
# 기본 패키지
sudo apt install -y rpicam-apps ffmpeg python3-opencv

# Picamera2 관련 패키지
sudo apt install -y python3-picamera2 python3-libcamera

# GPU 메모리 설정 (권장: 256MB)
sudo raspi-config  # Advanced Options → Memory Split → 256
```

### 참고 문서
- [Raspberry Pi Camera Documentation](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [OpenCV Python Tutorials](https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html)
- [ffmpeg Documentation](https://ffmpeg.org/documentation.html)

### 코딩 컨벤션
- **Python**: PEP 8 준수
- **함수명**: snake_case
- **클래스명**: PascalCase
- **상수**: UPPER_CASE
- **주석**: 한국어 + 영어 혼용

### Git 워크플로우
```bash
# 기능 브랜치
git checkout -b feature/new-detection-algorithm
git commit -m "feat: implement advanced motion detection"
git push origin feature/new-detection-algorithm
```

---

## 기여 가이드

### 코드 기여
1. 이슈 생성 및 논의
2. 기능 브랜치 생성
3. 코드 작성 및 테스트
4. 문서 업데이트
5. Pull Request 생성

### 문서 기여
- **PRD.md**: 제품 요구사항 및 아키텍처
- **README.md**: 사용자 가이드 및 설치 방법
- **CLAUDE.md**: 개발자 기술 문서 (현재 파일)

### 테스트 가이드
```bash
# CCTV 시스템 테스트
curl -I http://localhost:8001/stream  # 스트림 응답 확인
curl http://localhost:8001/api/stats  # 통계 API 테스트

# 녹화 시스템 테스트
ls -la videos/cam_rec/cam0/           # 녹화 파일 확인
ffprobe videos/cam_rec/cam0/*.mp4     # 영상 정보 확인

# GPU 가속 확인
dmesg | grep -i pisp                   # PiSP 하드웨어 가속 로그
```