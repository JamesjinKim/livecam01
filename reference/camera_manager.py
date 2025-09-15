#!/usr/bin/env python3
"""
중앙화된 카메라 관리자 - 단일 프로세스에서 모든 카메라 제어
ISP 리소스 경합 문제 완전 해결
"""

import asyncio
import threading
import time
from typing import Optional, Dict, Any
from enum import Enum
import logging
from queue import Queue, Empty
import io

try:
    from picamera2 import Picamera2
    from libcamera import Transform
    import libcamera
except ImportError as e:
    print(f"[ERROR] Picamera2 not installed: {e}")
    import sys
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CameraMode(Enum):
    """카메라 모드 정의"""
    IDLE = "idle"
    STREAMING = "streaming"
    RECORDING = "recording"
    DUAL_STREAMING = "dual_streaming"

class UnifiedCameraManager:
    """
    단일 프로세스에서 모든 카메라를 관리
    ISP 리소스 경합 문제를 근본적으로 해결
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        self.initialized = True
        self.cameras = {}  # {camera_id: Picamera2 instance}
        self.camera_modes = {}  # {camera_id: CameraMode}
        self.stream_queues = {}  # {camera_id: Queue}
        self.recording_handles = {}  # {camera_id: encoder}

        # 카메라 설정
        self.resolutions = {
            "480p": (640, 480),
            "720p": (1280, 720)
        }
        self.current_resolution = "480p"

        # 스레드 안전 잠금
        self.operation_lock = threading.Lock()

        logger.info("[INIT] 통합 카메라 관리자 초기화")

    def initialize_camera(self, camera_id: int, mode: CameraMode = CameraMode.IDLE) -> bool:
        """카메라 초기화 - 동시에 하나의 모드만 허용"""
        with self.operation_lock:
            try:
                # 기존 카메라가 있으면 정리
                if camera_id in self.cameras:
                    self.cleanup_camera(camera_id)

                # 다른 카메라가 녹화 중이면 RGB888 사용
                other_camera = 1 if camera_id == 0 else 0
                other_recording = (other_camera in self.camera_modes and
                                 self.camera_modes[other_camera] == CameraMode.RECORDING)

                # Picamera2 인스턴스 생성
                picam2 = Picamera2(camera_num=camera_id)

                width, height = self.resolutions[self.current_resolution]

                # 모드별 설정
                if mode == CameraMode.RECORDING:
                    # 녹화 모드 - 항상 YUV420 (H264 인코딩용)
                    config = picam2.create_video_configuration(
                        main={
                            "size": (width, height),
                            "format": "YUV420"
                        },
                        buffer_count=3,  # 녹화용 버퍼
                        queue=False
                    )
                else:
                    # 스트리밍 모드 - 상황에 따라 포맷 선택
                    if other_recording:
                        # 다른 카메라가 녹화 중이면 RGB888
                        format_str = "RGB888"
                    else:
                        # 일반 스트리밍은 MJPEG 최적화를 위해 RGB888
                        format_str = "RGB888"

                    config = picam2.create_video_configuration(
                        main={
                            "size": (width, height),
                            "format": format_str
                        },
                        transform=Transform(hflip=True),
                        buffer_count=2,  # 스트리밍용 버퍼
                        queue=False
                    )

                picam2.configure(config)
                picam2.start()

                # 상태 저장
                self.cameras[camera_id] = picam2
                self.camera_modes[camera_id] = mode

                if mode == CameraMode.STREAMING:
                    self.stream_queues[camera_id] = Queue(maxsize=2)

                logger.info(f"[OK] 카메라 {camera_id} 초기화 완료 (모드: {mode.value})")
                return True

            except Exception as e:
                logger.error(f"[ERROR] 카메라 {camera_id} 초기화 실패: {e}")
                return False

    def cleanup_camera(self, camera_id: int):
        """카메라 정리"""
        try:
            if camera_id in self.cameras:
                picam2 = self.cameras[camera_id]

                # 녹화 중이면 중지
                if camera_id in self.recording_handles:
                    encoder = self.recording_handles[camera_id]
                    picam2.stop_encoder(encoder)
                    del self.recording_handles[camera_id]

                # 카메라 중지
                picam2.stop()
                picam2.close()

                # 상태 정리
                del self.cameras[camera_id]
                if camera_id in self.camera_modes:
                    del self.camera_modes[camera_id]
                if camera_id in self.stream_queues:
                    del self.stream_queues[camera_id]

                logger.info(f"[OK] 카메라 {camera_id} 정리 완료")

        except Exception as e:
            logger.error(f"[ERROR] 카메라 {camera_id} 정리 실패: {e}")

    def switch_mode(self, camera_id: int, new_mode: CameraMode) -> bool:
        """카메라 모드 전환 - 스트리밍 ↔ 녹화"""
        with self.operation_lock:
            try:
                current_mode = self.camera_modes.get(camera_id, CameraMode.IDLE)

                if current_mode == new_mode:
                    return True

                logger.info(f"[SWITCH] 카메라 {camera_id}: {current_mode.value} → {new_mode.value}")

                # 카메라 재초기화 (모드 변경)
                self.cleanup_camera(camera_id)
                time.sleep(0.5)  # ISP 리셋 대기

                return self.initialize_camera(camera_id, new_mode)

            except Exception as e:
                logger.error(f"[ERROR] 모드 전환 실패: {e}")
                return False

    def capture_frame_for_streaming(self, camera_id: int) -> Optional[bytes]:
        """스트리밍용 프레임 캡처"""
        try:
            if camera_id not in self.cameras:
                return None

            if self.camera_modes.get(camera_id) != CameraMode.STREAMING:
                return None

            picam2 = self.cameras[camera_id]

            # JPEG 캡처
            stream = io.BytesIO()
            picam2.capture_file(stream, format='jpeg')
            return stream.getvalue()

        except Exception as e:
            logger.error(f"[ERROR] 프레임 캡처 실패: {e}")
            return None

    def start_recording(self, camera_id: int, output_path: str, duration: int = 30) -> bool:
        """녹화 시작"""
        with self.operation_lock:
            try:
                # 스트리밍 중이면 녹화 모드로 전환
                if self.camera_modes.get(camera_id) != CameraMode.RECORDING:
                    if not self.switch_mode(camera_id, CameraMode.RECORDING):
                        return False

                picam2 = self.cameras[camera_id]

                # H264 인코더 생성
                from picamera2.encoders import H264Encoder
                from picamera2.outputs import FfmpegOutput

                encoder = H264Encoder(bitrate=5000000)
                output = FfmpegOutput(output_path)
                encoder.output = output

                # 녹화 시작
                picam2.start_encoder(encoder)
                self.recording_handles[camera_id] = encoder

                logger.info(f"[OK] 카메라 {camera_id} 녹화 시작: {output_path}")

                # 지정된 시간 후 자동 중지 (별도 스레드)
                def auto_stop():
                    time.sleep(duration)
                    self.stop_recording(camera_id)

                threading.Thread(target=auto_stop, daemon=True).start()

                return True

            except Exception as e:
                logger.error(f"[ERROR] 녹화 시작 실패: {e}")
                return False

    def stop_recording(self, camera_id: int) -> bool:
        """녹화 중지"""
        with self.operation_lock:
            try:
                if camera_id not in self.recording_handles:
                    return False

                picam2 = self.cameras[camera_id]
                encoder = self.recording_handles[camera_id]

                # 녹화 중지
                picam2.stop_encoder(encoder)
                del self.recording_handles[camera_id]

                logger.info(f"[OK] 카메라 {camera_id} 녹화 중지")

                # 스트리밍 모드로 복귀
                return self.switch_mode(camera_id, CameraMode.STREAMING)

            except Exception as e:
                logger.error(f"[ERROR] 녹화 중지 실패: {e}")
                return False

    def get_status(self) -> Dict[str, Any]:
        """전체 상태 반환"""
        return {
            "cameras": {
                cam_id: {
                    "mode": mode.value,
                    "recording": cam_id in self.recording_handles
                }
                for cam_id, mode in self.camera_modes.items()
            },
            "resolution": self.current_resolution
        }

    def cleanup_all(self):
        """모든 카메라 정리"""
        with self.operation_lock:
            for camera_id in list(self.cameras.keys()):
                self.cleanup_camera(camera_id)
            logger.info("[OK] 모든 카메라 정리 완료")


# 싱글톤 인스턴스
camera_manager = UnifiedCameraManager()


if __name__ == "__main__":
    # 테스트 코드
    manager = camera_manager

    print("통합 카메라 관리자 테스트")
    print("=" * 50)

    # 카메라 0 스트리밍 모드
    if manager.initialize_camera(0, CameraMode.STREAMING):
        print("✓ 카메라 0 스트리밍 모드 초기화 성공")

    # 카메라 1 스트리밍 모드
    if manager.initialize_camera(1, CameraMode.STREAMING):
        print("✓ 카메라 1 스트리밍 모드 초기화 성공")

    time.sleep(2)

    # 카메라 0을 녹화 모드로 전환
    if manager.switch_mode(0, CameraMode.RECORDING):
        print("✓ 카메라 0 녹화 모드 전환 성공")

    print("\n현재 상태:")
    print(manager.get_status())

    # 정리
    manager.cleanup_all()
    print("\n테스트 완료")