#!/usr/bin/env python3
"""
rpicam-vid + OpenCV를 이용한 간단한 모션 감지 (리팩토링 버전) - Camera 0
단일 책임 원칙 적용 - 각 기능을 별도 클래스로 분리

참고:
- https://github.com/markschnabel/opencv-motion-detector
- https://github.com/youngsoul/rpi-motion-detection-background-subtraction
- https://pyimagesearch.com/2015/05/25/basic-motion-detection-and-tracking-with-python-and-opencv/

날짜: 2025-09-05
"""

import cv2
import numpy as np
import subprocess
import time
import signal
import sys
import os
import threading
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

# ============================================================================
# 전역 설정 상수들 (한눈에 파악 가능)
# ============================================================================

# 모션 감지 민감도 설명 (참고용)
## very_low: 화면의 3~5% 이상이 변해야 감지(사람이 지나갈 때 정도)
## low: 팔 전체를 흔들거나 큰 동작만 감지(실내 조명 변화에 영향 없음)
## medium: 손 전체를 크게 흔들 때만 감지(일상적 손짓)
## high: 손가락 등 작은 움직임도 감지(노이즈에 민감, 조명 변화 영향 받음)
## very_high: 카메라 흔들림, 조명 변화, 노이즈까지 감지(실제 환경에서는 false positive 많음)
##
## 민감도 단계:1. 너무 예민함.
##
##  | 단계       | 임계값 | 쿨다운 | 설명                  |
##  |-----------|--------|-----|---------------------|
##  | very_low  | 5000px | 10초 | 매우 낮음 - 사람이 걸어다닐 때만 |
##  | low       | 2000px | 8초  | 낮음 - 큰 손짓만 (현재 설정)  |
##  | medium    | 1500px | 6초  | 보통 - 의도적인 손움직임만     |
##  | high      | 200px  | 3초  | 높음 - 작은 움직임도        |
##  | very_high | 50px   | 2초  | 매우 높음 - 카메라 흔들림도    |

## 민감도 단계:2. 많이 덜 예민함. 조정값.
##
##  | 단계       | 임계값 | 쿨다운 | 설명                              |
##  |-----------|--------|-------|---------------------------------|
##  | very_low  | 10000px| 10초  | 매우 낮음 - 사람이 화면을 가로질러야 감지됨   |
##  | low       | 6000px | 8초   | 낮음 - 팔 전체를 흔들 때만 감지           |
##  | medium    | 3500px | 6초   | 보통 - 손 전체를 크게 흔들 때만 감지       |
##  | high      | 1200px | 3초   | 높음 - 손가락 움직임 등 작은 움직임도 감지   |
##  | very_high | 300px  | 2초   | 매우 높음 - 미세한 변화, 노이즈도 감지      |
##

# 모션 감지 민감도 단계 (조명 변화와 노이즈에 둔감하게, 실제 사람 팔 움직임만 감지)
SENSITIVITY_LEVELS = {
    'very_low': {
        'threshold': 15000,     # 매우 높은 임계값 - 사람이 화면을 크게 가로질러야 감지
        'cooldown': 15,         # 감지 후 대기 시간 김 (더 길게)
        'description': '매우 낮음 - 사람이 화면을 거의 다 가로질러야 감지'
    },
    'low': {
        'threshold': 10000,     # 높은 임계값 - 팔 전체를 크게 흔들 때 감지 (더 높게)
        'cooldown': 12,         # 대기 시간 김
        'description': '낮음 - 팔 전체를 크게 흔들 때 정도 감지'
    },
    'medium': {
        'threshold': 6000,      # 보통 임계값 - 팔이나 손 전체가 움직일 때 감지 (더 높게)
        'cooldown': 8,          # 대기 시간 김
        'description': '보통 - 팔이나 손 전체가 움직일 때만 감지'
    },
    'high': {
        'threshold': 3000,      # 낮은 임계값 - 손가락 등 작은 움직임도 감지 (더 높게)
        'cooldown': 5,          # 대기 시간 짧음
        'description': '높음 - 손가락 등 작은 물체 움직임도 감지'
    },
    'very_high': {
        'threshold': 1000,      # 매우 낮은 임계값 - 미세한 변화, 노이즈도 감지 (더 높게)
        'cooldown': 3,          # 매우 짧은 대기 시간
        'description': '매우 높음 - 미세한 변화, 노이즈까지 감지'
    }
}

# 현재 민감도 단계 설정
CURRENT_SENSITIVITY = 'low'  # very_low, low, medium, high, very_high 중에서 선택

# 모션 감지기 타입 설정
DETECTOR_TYPE = 'simple'  # simple, hand_wave 중에서 선택

# 카메라 설정
CAMERA_ID = 0  # Camera 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FRAMERATE = 30

# 영상 녹화 설정
RECORDING_ENABLED = True  # 모션 감지 시 영상 녹화 활성화
RECORDING_WIDTH = 1280    # 녹화 해상도 가로
RECORDING_HEIGHT = 720    # 녹화 해상도 세로
RECORDING_DURATION = 30   # 총 녹화 시간(초) - 프리버퍼 5초 + 포스트 25초
PRE_BUFFER_DURATION = 5   # 모션 감지 이전 버퍼 시간(초) - 5초로 설정
POST_BUFFER_DURATION = 25 # 모션 감지 이후 녹화 시간(초) - 25초로 설정

# 프레임 건너뛰기 및 배경 업데이트 주기 상수화
SKIP_FRAME = 3
BG_UPDATE_FAST = 10
BG_UPDATE_SLOW = 30

# 디버그 설정
DEBUG_OUTPUT = True       # 디버그 정보 출력
SHOW_VIDEO = False        # 실시간 영상 창 표시 (원격에서는 비활성화)

# ============================================================================
# 1. 설정 관리 클래스 (NEW)
# ============================================================================

class Config:
    """설정 관리 클래스"""
    
    def __init__(self, config_dict: dict = None):
        if config_dict is None:
            config_dict = self._get_default_config()
        
        self.camera = config_dict.get('camera', {})
        self.detection = config_dict.get('detection', {})
        self.recording = config_dict.get('recording', {})
        self.debug = config_dict.get('debug', {})
        
        # 민감도 설정 적용
        self._apply_sensitivity_settings()
    
    def _get_default_config(self) -> dict:
        """기본 설정 반환 (전역 상수 사용)"""
        return {
            'camera': {
                'id': CAMERA_ID,
                'width': FRAME_WIDTH,
                'height': FRAME_HEIGHT,
                'framerate': FRAMERATE
            },
            'detection': {
                'type': DETECTOR_TYPE,        # simple, hand_wave
                'sensitivity': CURRENT_SENSITIVITY,  # very_low, low, medium, high, very_high
                'skip_frames': SKIP_FRAME
            },
            'recording': {
                'enabled': RECORDING_ENABLED,
                'width': RECORDING_WIDTH,
                'height': RECORDING_HEIGHT,
                'duration': RECORDING_DURATION,
                'pre_buffer': PRE_BUFFER_DURATION,
                'post_buffer': POST_BUFFER_DURATION,
                'output_dir': 'videos/motion_events/cam0'  # cam0 디렉토리
            },
            'debug': {
                'output': DEBUG_OUTPUT,
                'show_video': SHOW_VIDEO
            }
        }
    
    def _apply_sensitivity_settings(self):
        """민감도 설정에 따라 threshold와 cooldown 적용"""
        sensitivity = self.detection.get('sensitivity', CURRENT_SENSITIVITY)
        
        if sensitivity in SENSITIVITY_LEVELS:
            sensitivity_config = SENSITIVITY_LEVELS[sensitivity]
            self.detection['threshold'] = sensitivity_config['threshold']
            self.detection['cooldown'] = sensitivity_config['cooldown']
            self.detection['description'] = sensitivity_config['description']
        else:
            # 기본값 (CURRENT_SENSITIVITY 설정)
            default_config = SENSITIVITY_LEVELS[CURRENT_SENSITIVITY]
            self.detection['threshold'] = default_config['threshold']
            self.detection['cooldown'] = default_config['cooldown']
            self.detection['description'] = default_config['description']
    
    def get_sensitivity_info(self) -> str:
        """현재 민감도 정보 반환"""
        sensitivity = self.detection.get('sensitivity', CURRENT_SENSITIVITY)
        threshold = self.detection.get('threshold', 7000)
        cooldown = self.detection.get('cooldown', 8)
        description = self.detection.get('description', '')
        
        return f"민감도: {sensitivity.upper()} | 임계값: {threshold}px | 쿨다운: {cooldown}s | {description}"
    
    def list_available_sensitivities(self) -> str:
        """사용 가능한 민감도 목록 반환"""
        info_lines = ["사용 가능한 민감도 설정:"]
        for level, config in SENSITIVITY_LEVELS.items():
            current_mark = " ← 현재 설정" if level == CURRENT_SENSITIVITY else ""
            info_lines.append(f"  {level}: {config['threshold']}px, {config['cooldown']}s - {config['description']}{current_mark}")
        return "\n".join(info_lines)

# ============================================================================
# 2. 카메라 스트림 관리 클래스 (EXTRACTED from SimpleMotionDetector)
# ============================================================================

class CameraStreamManager:
    """카메라 스트림 관리 전담 클래스"""
    
    def __init__(self, camera_id: int = 0, width: int = 640, height: int = 480, framerate: int = 30):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.framerate = framerate
        self.process = None
        self.buffer = b""
        
    def start_stream(self) -> bool:
        """rpicam-vid MJPEG 스트림 시작"""
        cmd = [
            "rpicam-vid",
            "--camera", str(self.camera_id),
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.framerate),
            "--timeout", "0",  # 무한
            "--nopreview",
            "--codec", "mjpeg",
            "--quality", "80",
            "--flush", "1",
            "--output", "-"  # stdout
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                preexec_fn=os.setsid
            )
            print("Camera stream started")
            return True
        except Exception as e:
            print(f"Failed to start camera: {e}")
            return False
    
    def stop_stream(self):
        """카메라 스트림 중지"""
        if self.process and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=3)
            except:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except:
                    pass
        self.process = None
        self.buffer = b""
    
    def restart_stream(self) -> bool:
        """스트림 재시작"""
        self.stop_stream()
        time.sleep(2)
        return self.start_stream()
    
    def is_streaming(self) -> bool:
        """스트림 상태 확인"""
        return self.process is not None and self.process.poll() is None
    
    def get_frame(self) -> Optional[np.ndarray]:
        """다음 프레임 반환"""
        if not self.is_streaming():
            return None
            
        try:
            chunk = self.process.stdout.read(4096)
            if not chunk:
                return None
        except Exception:
            return None

        self.buffer += chunk
        
        frame, self.buffer = self._extract_frame_from_mjpeg(self.buffer)
        return frame
    
    def _extract_frame_from_mjpeg(self, buffer: bytes) -> tuple:
        """MJPEG 스트림에서 JPEG 프레임 추출"""
        start_marker = b'\xff\xd8'  # JPEG 시작
        end_marker = b'\xff\xd9'    # JPEG 끝

        start_pos = buffer.find(start_marker)
        end_pos = buffer.find(end_marker, start_pos)

        if start_pos >= 0 and end_pos > start_pos:
            jpeg_data = buffer[start_pos:end_pos + 2]
            remaining_buffer = buffer[end_pos + 2:]

            try:
                frame = cv2.imdecode(np.frombuffer(jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                return frame, remaining_buffer
            except:
                return None, remaining_buffer

        return None, buffer

    def test_camera(self) -> bool:
        """카메라 테스트"""
        test_cmd = ["rpicam-hello", "--camera", str(self.camera_id), "--timeout", "1000"]
        try:
            result = subprocess.run(test_cmd, capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False

# ============================================================================
# 3. 모션 감지 알고리즘 클래스들 (EXTRACTED from SimpleMotionDetector)
# ============================================================================

class MotionDetectorBase(ABC):
    """모션 감지기 추상 기본 클래스"""
    
    @abstractmethod
    def detect(self, frame: np.ndarray) -> bool:
        """모션 감지 수행"""
        pass
    
    @abstractmethod
    def reset(self):
        """감지기 상태 초기화"""
        pass
    
    @abstractmethod
    def is_ready(self) -> bool:
        """감지기 준비 상태 확인"""
        pass

class SimpleMotionDetector(MotionDetectorBase):
    """단순 배경 차분법 모션 감지기"""
    
    def __init__(self, threshold: int = 7000, cooldown: int = 8, debug: bool = True):
        self.threshold = threshold
        self.cooldown = cooldown
        self.debug = debug
        self.last_detection_time = 0
        self.background_frame = None
        self.background_frames = deque(maxlen=60)
        self.background_ready = False
        self.frame_count = 0
        
        # 상수들
        self.GAUSSIAN_BLUR_SIZE = 11
        self.DELTA_THRESHOLD = 25
        self.BG_UPDATE_FAST = 10
        self.BG_UPDATE_SLOW = 30
        
    def detect(self, frame: np.ndarray) -> bool:
        """단순 모션 감지"""
        current_time = time.time()
        self.frame_count += 1
        
        # 쿨다운 체크
        if current_time - self.last_detection_time < self.cooldown:
            return False

        # 그레이스케일 변환 및 블러
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.GAUSSIAN_BLUR_SIZE, self.GAUSSIAN_BLUR_SIZE), 0)

        # 배경 안정화 (60프레임)
        if len(self.background_frames) < 60:
            self.background_frames.append(gray.copy())
            if len(self.background_frames) == 60:
                self.background_frame = np.median(self.background_frames, axis=0).astype(np.uint8)
                self.background_ready = True
                if self.debug:
                    print("Background stabilized with 60 frames - motion detection active")
            return False

        if not self.background_ready:
            return False

        # 프레임 차이 계산
        frame_delta = cv2.absdiff(self.background_frame, gray)
        thresh = cv2.threshold(frame_delta, self.DELTA_THRESHOLD, 255, cv2.THRESH_BINARY)[1]

        # 변화한 픽셀 수 계산
        changed_pixels = cv2.countNonZero(thresh)

        # 디버그 출력
        if self.debug and self.frame_count % 10 == 0:
            print(f"Simple Debug: {changed_pixels} changed pixels")

        # 임계값 이상 변화 감지 시
        if changed_pixels > self.threshold:
            if self.debug:
                print(f"Motion detected: {changed_pixels} changed pixels")
            self.last_detection_time = current_time
            return True

        # 적응형 배경 업데이트
        if self.frame_count % self.BG_UPDATE_FAST == 0:
            self.background_frame = cv2.addWeighted(self.background_frame, 0.95, gray, 0.05, 0)

        return False
    
    def reset(self):
        """감지기 상태 초기화"""
        self.background_frame = None
        self.background_frames.clear()
        self.background_ready = False
        self.frame_count = 0
        self.last_detection_time = 0
    
    def is_ready(self) -> bool:
        """감지기 준비 상태"""
        return self.background_ready

class HandWaveDetector(MotionDetectorBase):
    """손 흔들기 패턴 감지기"""
    
    def __init__(self, cooldown: int = 8, debug: bool = True):
        self.cooldown = cooldown
        self.debug = debug
        self.last_detection_time = 0
        self.background_frame = None
        self.background_frames = deque(maxlen=30)
        self.background_ready = False
        self.hand_positions = []
        self.frame_count = 0
        
        # 손 감지 파라미터
        self.HAND_MIN_AREA = 800
        self.HAND_MAX_AREA = 80000
        self.GAUSSIAN_BLUR_SIZE = 11
        self.DELTA_THRESHOLD = 25
        self.WAVE_PATTERN_FRAMES = 4
        self.MOVEMENT_THRESHOLD = 15
    
    def detect(self, frame: np.ndarray) -> bool:
        """손 흔들기 감지"""
        current_time = time.time()
        self.frame_count += 1

        # 쿨다운 체크
        if current_time - self.last_detection_time < self.cooldown:
            return False

        # 그레이스케일 변환
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.GAUSSIAN_BLUR_SIZE, self.GAUSSIAN_BLUR_SIZE), 0)

        # 배경 안정화 단계 (처음 30프레임)
        if len(self.background_frames) < 30:
            self.background_frames.append(gray.copy())
            if len(self.background_frames) == 30:
                self.background_frame = np.median(self.background_frames, axis=0).astype(np.uint8)
                self.background_ready = True
                if self.debug:
                    print("Background stabilized - hand wave detection active")
            return False

        if not self.background_ready:
            return False

        # 배경과 현재 프레임의 차이 계산
        frame_delta = cv2.absdiff(self.background_frame, gray)
        thresh = cv2.threshold(frame_delta, self.DELTA_THRESHOLD, 255, cv2.THRESH_BINARY)[1]

        # 노이즈 제거 및 손 형태 보존
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # 컨투어 찾기
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 손 모양 후보 찾기
        hand_candidates = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if self.HAND_MIN_AREA <= area <= self.HAND_MAX_AREA:
                perimeter = cv2.arcLength(contour, True)
                if perimeter > 0:
                    compactness = (4 * np.pi * area) / (perimeter * perimeter)
                    if 0.1 < compactness < 0.9:
                        M = cv2.moments(contour)
                        if M["m00"] > 0:
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"])
                            hand_candidates.append({
                                'center': (cx, cy),
                                'area': area,
                                'contour': contour,
                                'compactness': compactness
                            })

        # 손 위치 추적 및 패턴 분석
        if hand_candidates:
            largest_hand = max(hand_candidates, key=lambda x: x['area'])
            self.hand_positions.append(largest_hand['center'])

            if len(self.hand_positions) > self.WAVE_PATTERN_FRAMES:
                self.hand_positions.pop(0)

            if len(self.hand_positions) >= self.WAVE_PATTERN_FRAMES:
                wave_detected = self._analyze_wave_pattern()
                if wave_detected:
                    self.last_detection_time = current_time
                    self.hand_positions.clear()
                    return True
        else:
            if len(self.hand_positions) > 0:
                self.hand_positions.pop(0)

        # 느린 배경 업데이트
        if self.frame_count % 20 == 0:
            self.background_frame = cv2.addWeighted(self.background_frame, 0.95, gray, 0.05, 0)

        return False
    
    def _analyze_wave_pattern(self) -> bool:
        """손 위치로 흔들기 패턴 분석"""
        if len(self.hand_positions) < self.WAVE_PATTERN_FRAMES:
            return False

        x_positions = [pos[0] for pos in self.hand_positions]
        x_min, x_max = min(x_positions), max(x_positions)
        x_range = x_max - x_min

        if x_range < self.MOVEMENT_THRESHOLD:
            return False

        direction_changes = 0
        for i in range(1, len(x_positions) - 1):
            if ((x_positions[i] > x_positions[i-1] and x_positions[i] > x_positions[i+1]) or
                (x_positions[i] < x_positions[i-1] and x_positions[i] < x_positions[i+1])):
                direction_changes += 1

        if direction_changes >= 1:
            if self.debug:
                print(f"Wave pattern detected: range={x_range}px, changes={direction_changes}")
            return True

        return False
    
    def reset(self):
        """감지기 상태 초기화"""
        self.background_frame = None
        self.background_frames.clear()
        self.background_ready = False
        self.hand_positions.clear()
        self.frame_count = 0
        self.last_detection_time = 0
    
    def is_ready(self) -> bool:
        """감지기 준비 상태"""
        return self.background_ready

# ============================================================================
# 4. 영상 녹화 관리 클래스 (EXTRACTED from SimpleMotionDetector)
# ============================================================================

class VideoRecorder:
    """프리버퍼링을 지원하는 영상 녹화 전담 클래스"""
    
    def __init__(self, output_dir: str = "videos/motion_events/cam0", 
                 width: int = 1280, height: int = 720, 
                 pre_buffer: int = 10, post_buffer: int = 20):
        self.output_dir = Path(output_dir)
        self.width = width
        self.height = height
        self.pre_buffer = pre_buffer    # 모션 이전 버퍼 시간
        self.post_buffer = post_buffer  # 모션 이후 녹화 시간
        self.duration = pre_buffer + post_buffer  # 총 녹화 시간
        
        self.is_recording = False
        self.recording_process = None
        self.current_recording_path = None
        self.current_temp_files = []  # 현재 처리 중인 임시 파일들
        self.merge_thread = None  # 병합 스레드 추적
        self.merge_thread_stop = threading.Event()  # 스레드 종료 신호
        
        # 프리버퍼링을 위한 변수 (프레임 기반)
        self.buffer_dir = None
        # skip_frames를 고려한 실제 fps 계산 (30fps / 3 = 10fps)
        self.actual_buffer_fps = FRAMERATE // SKIP_FRAME  # 30 / 3 = 10fps
        self.frame_buffer = deque(maxlen=pre_buffer * self.actual_buffer_fps)  # 5초 * 10fps = 50 프레임
        self.buffer_lock = threading.Lock()
        self.frame_count = 0
        self.last_buffer_save_time = 0
        
        # 출력 디렉토리 생성
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 임시 디렉토리 생성
        self.buffer_dir = Path(tempfile.mkdtemp(prefix="motion_buffer_"))
    
    def add_frame_to_buffer(self, frame: np.ndarray):
        """프레임을 버퍼에 추가 (모션 감지 스트림에서 호출)"""
        with self.buffer_lock:
            # JPEG로 인코딩하여 저장 (메모리 효율)
            _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            self.frame_buffer.append(jpeg_data)
            self.frame_count += 1
            
            # 1초마다 버퍼 상태 출력
            current_time = time.time()
            if current_time - self.last_buffer_save_time >= 1:
                buffer_seconds = len(self.frame_buffer) / self.actual_buffer_fps  # 실제 저장 fps로 계산
                if self.frame_count % 10 == 0:  # 10fps 기준으로 변경
                    print(f"Buffer: {buffer_seconds:.1f}s ({len(self.frame_buffer)} frames @ {self.actual_buffer_fps}fps)")
                self.last_buffer_save_time = current_time
    
    def save_buffer_to_file(self) -> Optional[Path]:
        """현재 버퍼를 파일로 저장"""
        if not self.frame_buffer:
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        buffer_file = self.buffer_dir / f"buffer_{timestamp}.mp4"
        
        try:
            # OpenCV VideoWriter 사용 - 30fps로 설정 (호환성을 위해)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(str(buffer_file), fourcc, 30.0, (self.width, self.height))  # 30fps로 설정
            
            # 프레임 보간: 10fps → 30fps (3배 복사)
            frame_duplication = 3  # 30fps / 10fps = 3
            
            with self.buffer_lock:
                for jpeg_data in self.frame_buffer:
                    frame = cv2.imdecode(jpeg_data, cv2.IMREAD_COLOR)
                    if frame is not None:
                        # 해상도 변환 (640x480 -> 1280x720)
                        frame_resized = cv2.resize(frame, (self.width, self.height))
                        # 같은 프레임을 3번 쓰기 (10fps → 30fps 변환)
                        for _ in range(frame_duplication):
                            out.write(frame_resized)
            
            out.release()
            
            if buffer_file.exists():
                # 버퍼 파일 크기와 예상 시간 출력
                file_size = buffer_file.stat().st_size / (1024 * 1024)
                frames_saved = len(self.frame_buffer)
                expected_seconds = frames_saved / self.actual_buffer_fps
                
                # 프리버퍼 duration 확인
                duration_check = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(buffer_file)],
                    capture_output=True, timeout=5
                )
                
                if duration_check.returncode == 0:
                    actual_duration = float(duration_check.stdout.decode().strip())
                    print(f"Pre-buffer saved: {buffer_file.name}")
                    print(f"  - Frames: {frames_saved} frames @ {self.actual_buffer_fps}fps capture")
                    print(f"  - Duration: {actual_duration:.1f}s (expected: {expected_seconds:.1f}s)")
                    print(f"  - File size: {file_size:.1f}MB")
                    
                    # Duration 경고
                    if abs(actual_duration - expected_seconds) > 0.5:
                        print(f"  ⚠️ Warning: Duration mismatch! Check fps settings.")
                else:
                    print(f"Pre-buffer saved: {buffer_file.name} ({file_size:.1f}MB, {frames_saved} frames = {expected_seconds:.1f}s)")
                
                return buffer_file
            else:
                return None
                
        except Exception as e:
            print(f"Buffer save error: {e}")
            return None
    
    def cleanup_buffer(self):
        """버퍼 정리"""
        if self.buffer_dir and self.buffer_dir.exists():
            try:
                shutil.rmtree(self.buffer_dir)
            except:
                pass
        self.frame_buffer.clear()
        
        # 병합 스레드 종료 신호
        self.merge_thread_stop.set()
    
    def cleanup_temp_files(self):
        """모든 임시 파일 정리"""
        # 추적 중인 임시 파일 삭제
        for temp_file in self.current_temp_files:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                    print(f"Cleaned up temp file: {temp_file.name}")
                except Exception as e:
                    print(f"Failed to delete temp file {temp_file.name}: {e}")
        
        # output_dir 및 하위 날짜 폴더의 모든 temp_*.h264 파일 정리
        if self.output_dir.exists():
            # 메인 디렉토리의 임시 파일
            for temp_file in self.output_dir.glob("temp_*.h264"):
                try:
                    temp_file.unlink()
                    print(f"Cleaned up orphaned temp file: {temp_file.name}")
                except Exception as e:
                    print(f"Failed to delete temp file {temp_file.name}: {e}")
            
            # 날짜 폴더 내의 임시 파일
            for date_folder in self.output_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9]"):
                for temp_file in date_folder.glob("temp_*.h264"):
                    try:
                        temp_file.unlink()
                        print(f"Cleaned up temp file: {date_folder.name}/{temp_file.name}")
                    except Exception as e:
                        print(f"Failed to delete temp file: {e}")
        
        # concat 리스트 파일 정리
        if self.output_dir.exists():
            # 메인 디렉토리의 concat 파일
            for list_file in self.output_dir.glob("concat_*.txt"):
                try:
                    list_file.unlink()
                    print(f"Cleaned up list file: {list_file.name}")
                except Exception as e:
                    print(f"Failed to delete list file {list_file.name}: {e}")
            
            # 날짜 폴더 내의 concat 파일
            for date_folder in self.output_dir.glob("[0-9][0-9][0-9][0-9][0-9][0-9]"):
                for list_file in date_folder.glob("concat_*.txt"):
                    try:
                        list_file.unlink()
                        print(f"Cleaned up list file: {date_folder.name}/{list_file.name}")
                    except Exception as e:
                        print(f"Failed to delete list file: {e}")
        
        self.current_temp_files.clear()
    
    def start_recording(self, camera_id: int) -> Optional[Path]:
        """프리버퍼와 포스트 녹화를 병합한 영상 녹화"""
        if self.is_recording:
            return None
            
        # 날짜별 폴더 생성 (YYMMDD 형식)
        now = datetime.now()
        date_folder = now.strftime("%y%m%d")  # YYMMDD 형식
        daily_dir = self.output_dir / date_folder
        daily_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        output_path = daily_dir / f"motion_event_cam0_{timestamp}.mp4"  # 날짜 폴더 안에 저장
        self.current_recording_path = output_path
        
        print("\n" + "="*60)
        print(f"🎬 Motion Event Recording Started")
        print(f"  Pre-buffer: {self.pre_buffer}s (from circular buffer)")
        print(f"  Post-buffer: {self.post_buffer}s (new recording)")
        print(f"  Expected total: {self.pre_buffer + self.post_buffer}s")
        print("="*60)
        
        try:
            self.is_recording = True
            
            # 1. 현재 버퍼 저장
            buffer_file = self.save_buffer_to_file()
            
            if not buffer_file:
                print("Warning: No pre-buffer available")
            
            # 2. 포스트 버퍼 녹화 (스트림 중단 필요)
            temp_post_file = daily_dir / f"temp_post_{timestamp}.h264"  # 날짜 폴더에 임시 파일 생성
            self.current_temp_files.append(temp_post_file)  # 임시 파일 추적
            
            recording_cmd = [
                "rpicam-vid",
                "--camera", str(camera_id),
                "--width", str(self.width),
                "--height", str(self.height),
                "--framerate", "30",  # 30fps로 통일
                "--timeout", str(self.post_buffer * 1000),
                "--nopreview",
                "--codec", "h264",
                "--output", str(temp_post_file)
            ]
            
            print(f"Recording {self.post_buffer}s post-buffer...")
            self.recording_process = subprocess.Popen(
                recording_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            # 3. 백그라운드에서 병합 작업 수행
            def merge_worker():
                try:
                    # 포스트 버퍼 녹화 완료 대기
                    self.recording_process.wait(timeout=self.post_buffer + 5)
                    
                    if temp_post_file.exists():
                        # 파일 병합
                        files_to_merge = []
                        if buffer_file and buffer_file.exists():
                            files_to_merge.append(buffer_file)
                        files_to_merge.append(temp_post_file)
                        
                        if len(files_to_merge) > 1:
                            print(f"\n📼 Merging videos:")
                            print(f"  1. Pre-buffer: {buffer_file.name if buffer_file else 'None'} ({self.pre_buffer}s)")
                            print(f"  2. Post-buffer: {temp_post_file.name} ({self.post_buffer}s)")
                            self._merge_video_files(files_to_merge, output_path)
                        else:
                            # 버퍼가 없으면 포스트 파일만 사용
                            print(f"⚠️ No pre-buffer available, using post-buffer only ({self.post_buffer}s)")
                            shutil.move(str(temp_post_file), str(output_path))
                        
                        # 임시 파일 삭제
                        if temp_post_file.exists():
                            temp_post_file.unlink()
                        if buffer_file and buffer_file.exists():
                            buffer_file.unlink()
                        
                        print(f"Recording saved: {output_path.name}")
                    else:
                        print("Post-buffer recording failed")
                        
                except Exception as e:
                    print(f"Merge error: {e}")
                finally:
                    self.is_recording = False
                    self.current_recording_path = None
                    self.current_temp_files.clear()  # 임시 파일 목록 정리
            
            # 병합 스레드 시작 (daemon=False로 변경하여 정상 종료 보장)
            self.merge_thread = threading.Thread(target=merge_worker, daemon=False)
            self.merge_thread.start()
            
            return output_path
            
        except Exception as e:
            print(f"Recording error: {e}")
            self.is_recording = False
            return None
    
    def _merge_video_files(self, input_files: List[Path], output_file: Path):
        """여러 비디오 파일을 하나의 MP4로 병합"""
        try:
            # 파일 리스트 생성
            list_file = output_file.parent / f"concat_{output_file.stem}.txt"
            with open(list_file, 'w') as f:
                for file in input_files:
                    if file.exists():
                        # mp4와 h264 파일 처리
                        if file.suffix == '.mp4':
                            # mp4를 h264로 변환 (프레임레이트 통일)
                            temp_h264 = file.parent / f"{file.stem}.h264"
                            extract_cmd = [
                                "ffmpeg", "-i", str(file),
                                "-c:v", "copy", "-an",
                                "-r", "30",  # 30fps로 통일
                                "-y", str(temp_h264)
                            ]
                            subprocess.run(extract_cmd, capture_output=True, timeout=15)
                            if temp_h264.exists():
                                f.write(f"file '{temp_h264.absolute()}'\n")
                        else:
                            f.write(f"file '{file.absolute()}'\n")
            
            # ffmpeg으로 병합 (30초로 제한)
            merge_cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c:v", "libx264",  # h264 코덱 사용
                "-preset", "fast",  # 인코딩 속도 향상
                "-t", "30",         # 30초로 제한
                "-r", "30",         # 30fps로 통일
                "-pix_fmt", "yuv420p",  # 호환성 향상
                "-y",
                str(output_file)
            ]
            
            result = subprocess.run(merge_cmd, capture_output=True, timeout=60)  # 30초 → 60초로 증가
            
            # 임시 파일 정리
            list_file.unlink()
            for file in input_files:
                if file.suffix == '.mp4':
                    temp_h264 = file.parent / f"{file.stem}.h264"
                    if temp_h264.exists():
                        temp_h264.unlink()
            
            if result.returncode == 0:
                file_size = output_file.stat().st_size / (1024 * 1024)
                
                # 병합된 비디오의 실제 duration 확인
                duration_check = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(output_file)],
                    capture_output=True, timeout=5
                )
                
                if duration_check.returncode == 0:
                    actual_duration = float(duration_check.stdout.decode().strip())
                    print(f"\n✅ Video merged successfully: {output_file.name}")
                    print(f"  - File size: {file_size:.1f}MB")
                    print(f"  - Final duration: {actual_duration:.1f}s")
                    print(f"  - Expected: 30s (pre:{self.pre_buffer}s + post:{self.post_buffer}s)")
                    print(f"  - Difference: {actual_duration-30:+.1f}s")
                    
                    # 프리버퍼 포함 여부 확인
                    if abs(actual_duration - 30) < 0.5:
                        print(f"  ✓ Pre-buffer successfully included in final video")
                    elif actual_duration < 28:
                        print(f"  ⚠️ Pre-buffer may be missing or incomplete")
                    else:
                        print(f"  ✓ Duration check passed")
                else:
                    print(f"\n✅ Video merged: {output_file.name} ({file_size:.1f}MB)")
                    print(f"  ⚠️ Duration verification failed")
                
                return True
            else:
                print(f"Merge failed: {result.stderr.decode()[:200]}")
                return False
                
        except Exception as e:
            print(f"Merge error: {e}")
            return False
    
    def wait_for_completion(self) -> bool:
        """녹화 완료 대기"""
        if not self.recording_process:
            return False
            
        try:
            stdout, stderr = self.recording_process.communicate(timeout=self.duration + 10)
            success = self.recording_process.returncode == 0
            self.is_recording = False
            self.current_recording_path = None  # 녹화 완료 시 경로 초기화
            return success
        except subprocess.TimeoutExpired:
            self.stop_recording()
            return False
    
    def stop_recording(self):
        """영상 녹화 중지"""
        if self.recording_process and self.recording_process.poll() is None:
            try:
                # SIGTERM 먼저 시도
                os.killpg(os.getpgid(self.recording_process.pid), signal.SIGTERM)
                try:
                    self.recording_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # SIGKILL로 강제 종료
                    os.killpg(os.getpgid(self.recording_process.pid), signal.SIGKILL)
                    self.recording_process.wait(timeout=1)
            except:
                pass
        
        # 병합 스레드 종료 대기
        if self.merge_thread and self.merge_thread.is_alive():
            print("Waiting for merge thread to complete...")
            self.merge_thread_stop.set()
            self.merge_thread.join(timeout=3)
            if self.merge_thread.is_alive():
                print("Warning: Merge thread still running")
        
        self.is_recording = False
        # current_recording_path는 check_and_cleanup_recording에서 처리
    
    def is_recording_active(self) -> bool:
        """녹화 상태 확인"""
        return self.is_recording
    
    def check_and_cleanup_recording(self) -> bool:
        """중단된 녹화 파일 확인 및 정리"""
        if not self.current_recording_path:
            return True
            
        file_path = self.current_recording_path
        
        # 파일이 존재하는지 확인
        if not file_path.exists():
            print(f"Recording file not found: {file_path.name}")
            self.current_recording_path = None
            return False
            
        # 파일 크기 확인 (최소 크기 1KB)
        file_size = file_path.stat().st_size
        if file_size < 1024:
            print(f"Recording file too small ({file_size} bytes), deleting: {file_path.name}")
            try:
                file_path.unlink()
                print(f"Deleted corrupted file: {file_path.name}")
            except Exception as e:
                print(f"Failed to delete corrupted file: {e}")
            self.current_recording_path = None
            return False
            
        # ffprobe로 파일 무결성 확인
        try:
            check_cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ]
            result = subprocess.run(check_cmd, capture_output=True, timeout=5)
            
            if result.returncode != 0:
                print(f"Recording file is corrupted, deleting: {file_path.name}")
                try:
                    file_path.unlink()
                    print(f"Deleted corrupted file: {file_path.name}")
                except Exception as e:
                    print(f"Failed to delete corrupted file: {e}")
                self.current_recording_path = None
                return False
            else:
                # 파일이 정상인 경우
                file_size_mb = file_size / (1024 * 1024)
                print(f"Recording file is valid: {file_path.name} ({file_size_mb:.1f}MB)")
                self.current_recording_path = None
                return True
                
        except subprocess.TimeoutExpired:
            print(f"ffprobe timeout, file may be corrupted: {file_path.name}")
            self.current_recording_path = None
            return False
        except FileNotFoundError:
            print("ffprobe not found, cannot verify file integrity")
            print(f"Recording file saved but not verified: {file_path.name}")
            self.current_recording_path = None
            return True
        except Exception as e:
            print(f"Error checking file integrity: {e}")
            self.current_recording_path = None
            return False

# ============================================================================
# 5. 이벤트 관리 클래스 (NEW)
# ============================================================================

class MotionEvent:
    """모션 감지 이벤트"""
    def __init__(self, timestamp: datetime, detector_type: str, confidence: float = 0.0):
        self.timestamp = timestamp
        self.detector_type = detector_type
        self.confidence = confidence
        self.video_path = None

class EventManager:
    """이벤트 관리 및 로깅"""
    
    def __init__(self, debug: bool = True):
        self.events = []
        self.debug = debug
    
    def handle_motion_detected(self, event: MotionEvent):
        """모션 감지 이벤트 처리"""
        self.events.append(event)
        if self.debug:
            timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] 모션이 디텍되었습니다. ({event.detector_type})")
    
    def handle_recording_completed(self, event: MotionEvent, video_path: Path, success: bool):
        """녹화 완료 이벤트 처리"""
        if success and video_path.exists():
            event.video_path = video_path
            file_size = video_path.stat().st_size / (1024 * 1024)
            if self.debug:
                print(f"Recording completed: {video_path.name} ({file_size:.1f}MB)")
        else:
            if self.debug:
                print(f"Recording failed: {video_path.name if video_path else 'Unknown'}")
    
    def get_recent_events(self, count: int = 10) -> List[MotionEvent]:
        """최근 이벤트 조회"""
        return self.events[-count:]

# ============================================================================
# 6. 모션 감지기 팩토리 (NEW)
# ============================================================================

class MotionDetectorFactory:
    """모션 감지기 생성 팩토리"""
    
    @staticmethod
    def create_detector(config: dict) -> MotionDetectorBase:
        """설정에 따라 적절한 감지기 생성"""
        detector_type = config.get('type', 'simple')
        threshold = config.get('threshold', 7000)
        cooldown = config.get('cooldown', 8)
        debug = config.get('debug', True)
        
        if detector_type == 'simple':
            return SimpleMotionDetector(threshold=threshold, cooldown=cooldown, debug=debug)
        elif detector_type == 'hand_wave':
            return HandWaveDetector(cooldown=cooldown, debug=debug)
        else:
            raise ValueError(f"Unknown detector type: {detector_type}")

# ============================================================================
# 7. 메인 시스템 조정자 클래스 (REPLACES SimpleMotionDetector)
# ============================================================================

class MotionDetectionSystem:
    """모션 감지 시스템 전체 조정자"""
    
    def __init__(self, config: Config):
        self.config = config
        self.running = False
        
        # 컴포넌트 초기화
        self.camera_manager = CameraStreamManager(
            camera_id=config.camera.get('id', 0),
            width=config.camera.get('width', 640),
            height=config.camera.get('height', 480),
            framerate=config.camera.get('framerate', 30)
        )
        
        self.motion_detector = MotionDetectorFactory.create_detector({
            'type': config.detection.get('type', 'simple'),
            'threshold': config.detection.get('threshold', 7000),
            'cooldown': config.detection.get('cooldown', 8),
            'debug': config.debug.get('output', True)
        })
        
        if config.recording.get('enabled', True):
            self.video_recorder = VideoRecorder(
                output_dir=config.recording.get('output_dir', 'videos/motion_events/cam0'),
                width=config.recording.get('width', 1280),
                height=config.recording.get('height', 720),
                pre_buffer=config.recording.get('pre_buffer', 10),
                post_buffer=config.recording.get('post_buffer', 20)
            )
        else:
            self.video_recorder = None
        
        self.event_manager = EventManager(debug=config.debug.get('output', True))
        
        # 시그널 핸들러 설정
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self._print_startup_info()
    
    def _print_startup_info(self):
        """시작 정보 출력"""
        print(f"Motion Detection System Initialized - Camera 0")
        print(f"   Camera: {self.config.camera.get('width')}x{self.config.camera.get('height')}")
        print(f"   Detector: {self.config.detection.get('type').upper()}")
        print(f"   {self.config.get_sensitivity_info()}")
        print(f"   Recording: {self.config.recording.get('enabled')}")
        if self.video_recorder:
            print(f"   Recording Resolution: {self.config.recording.get('width')}x{self.config.recording.get('height')}")
            print(f"   Pre-buffer: {self.config.recording.get('pre_buffer', 5)}s (@ {FRAMERATE//SKIP_FRAME}fps capture)")
            print(f"   Post-buffer: {self.config.recording.get('post_buffer', 25)}s (@ 30fps capture)")
            print(f"   Total Duration: {self.config.recording.get('duration', 30)}s")
        print()
        print("🔧 설정 변경 방법:")
        print("   민감도 변경: 코드 상단의 CURRENT_SENSITIVITY 변수를 수정하세요.")
        print("   감지기 변경: 코드 상단의 DETECTOR_TYPE 변수를 수정하세요.")
        print()
        print(self.config.list_available_sensitivities())
        print()
    
    def _signal_handler(self, _signum, _frame):
        """시그널 발생 시 안전하게 종료"""
        print("\nShutting down motion detection system...")
        
        # 녹화 중인 파일 확인 및 정리
        if self.video_recorder:
            if self.video_recorder.current_recording_path:
                print(f"Checking interrupted recording: {self.video_recorder.current_recording_path.name}")
            
            # 녹화 프로세스 종료
            self.video_recorder.stop_recording()
            time.sleep(1)  # 파일 쓰기 완료 대기
            
            if self.video_recorder.current_recording_path:
                self.video_recorder.check_and_cleanup_recording()
            
            # 임시 파일들 정리
            print("Cleaning up temporary files...")
            self.video_recorder.cleanup_temp_files()
        
        # 시스템 종료
        self.stop()
        
        # 모든 스레드 종료 대기
        print("Waiting for all threads to complete...")
        for thread in threading.enumerate():
            if thread != threading.main_thread() and thread.is_alive():
                thread.join(timeout=1)
        
        print("Shutdown complete")
        sys.exit(0)
    
    def start(self):
        """시스템 시작"""
        # 카메라 테스트
        print("Testing camera...")
        if not self.camera_manager.test_camera():
            print("Camera test failed")
            return False
        print("Camera OK")
        
        # 카메라 스트림 시작 (프리버퍼링과 모션 감지를 동시에 수행)
        if not self.camera_manager.start_stream():
            print("Failed to start camera stream")
            return False
        
        self.running = True
        print("Motion detection started (Ctrl+C to stop)")
        if self.video_recorder:
            actual_fps = FRAMERATE // SKIP_FRAME
            buffer_frames = self.config.recording.get('pre_buffer', 5) * actual_fps
            print(f"Pre-buffering enabled: {self.config.recording.get('pre_buffer', 5)}s circular buffer")
            print(f"  - Capture rate: {actual_fps}fps (every {SKIP_FRAME} frames)")
            print(f"  - Buffer capacity: {buffer_frames} frames")
        print("Monitoring for motion...")
        
        self._run_detection_loop()
        return True
    
    def stop(self):
        """시스템 중지"""
        self.running = False
        
        # 카메라 스트림 중지
        if self.camera_manager:
            self.camera_manager.stop_stream()
        
        if self.video_recorder:
            # 녹화 중인 경우 중지
            if self.video_recorder.is_recording:
                self.video_recorder.stop_recording()
                time.sleep(1)  # 파일 쓰기 완료 대기
                if self.video_recorder.current_recording_path:
                    self.video_recorder.check_and_cleanup_recording()
            
            # 버퍼 정리
            self.video_recorder.cleanup_buffer()
            
            # 임시 파일 정리
            self.video_recorder.cleanup_temp_files()
        
        print("Motion detection system stopped")
    
    def _run_detection_loop(self):
        """메인 감지 루프"""
        frame_count = 0
        skip_frames = self.config.detection.get('skip_frames', 3)
        
        try:
            while self.running:
                # 프로세스 생존 확인
                if not self.camera_manager.is_streaming():
                    print("Camera stream died")
                    break

                # 프레임 가져오기
                frame = self.camera_manager.get_frame()
                if frame is None:
                    continue

                frame_count += 1

                # 프리버퍼링에 프레임 추가 (녹화 활성화된 경우)
                if self.video_recorder and not self.video_recorder.is_recording:
                    self.video_recorder.add_frame_to_buffer(frame)
                
                # 프레임 건너뛰기(부하 감소)
                if frame_count % skip_frames != 0:
                    continue

                # 모션 감지
                motion_detected = self.motion_detector.detect(frame)

                if motion_detected:
                    # 이벤트 생성
                    event = MotionEvent(
                        timestamp=datetime.now(),
                        detector_type=type(self.motion_detector).__name__
                    )
                    
                    # 이벤트 처리
                    self.event_manager.handle_motion_detected(event)
                    
                    # 녹화 트리거 (동기식으로 변경)
                    if self.video_recorder:
                        self._trigger_recording_sync(event)

                # 300프레임마다 상태 출력
                if frame_count % 300 == 0:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] Processed {frame_count} frames")

        except KeyboardInterrupt:
            print("\nUser interrupted")
        except Exception as e:
            print(f"Detection error: {e}")
        finally:
            self.stop()
    
    def _trigger_recording_sync(self, event: MotionEvent):
        """프리버퍼와 포스트 녹화를 활용한 녹화 트리거"""
        # 포스트 버퍼 녹화를 위해 스트림 중지 필요
        print("Stopping detection stream for post-buffer recording...")
        self.camera_manager.stop_stream()
        
        # 녹화 수행 (프리버퍼 + 포스트버퍼)
        video_path = self.video_recorder.start_recording(self.camera_manager.camera_id)
        
        if video_path:
            # 포스트 버퍼 녹화 완료 대기 (백그라운드에서 진행)
            print(f"Post-buffer recording in progress...")
            time.sleep(self.config.recording.get('post_buffer', 20) + 2)
            
            self.event_manager.handle_recording_completed(event, video_path, True)
        
        # 스트림 재시작
        print("Restarting detection stream...")
        if self.camera_manager.restart_stream():
            print("Detection stream resumed")
        else:
            print("Failed to restart detection stream")
            self.running = False

# ============================================================================
# 8. 메인 함수 (MODIFIED)
# ============================================================================

def main():
    """메인 함수"""
    print("Motion Detection System - Camera 0")
    print("=" * 40)
    
    # 설정 로드
    config = Config()  # 기본 설정 사용
    
    # 시스템 시작
    system = MotionDetectionSystem(config)
    system.start()

if __name__ == "__main__":
    main()