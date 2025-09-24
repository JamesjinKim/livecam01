#!/usr/bin/env python3
"""
Picamera2 기반 CCTV 시스템 - 통합 버전
스트리밍과 녹화 기능이 통합된 최적화 버전
"""

import asyncio
import signal
import sys
import time
import threading
import atexit
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Set
import logging
import uvicorn

# Picamera2 imports
try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FfmpegOutput
    import libcamera
    import cv2
except ImportError as e:
    print(f"[ERROR] Picamera2 not installed: {e}")
    print("[INSTALL] Run: sudo apt install -y python3-picamera2")
    sys.exit(1)

# 웹 API 임포트
from web.api import CCTVWebAPI

# 설정 관리자 임포트
from config_manager import config_manager

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GPURecorder:
    """GPU 가속 H.264 녹화 클래스 - rec_dual.py 방식"""

    def __init__(self, camera_id: int, picam2_instance):
        self.camera_id = camera_id
        self.picam2 = picam2_instance  # 공유 Picamera2 인스턴스

        # 설정에서 저장 경로 가져오기
        storage_path = config_manager.get_storage_path(str(camera_id))
        self.save_dir = Path(storage_path)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # 녹화 상태
        self.is_recording = False
        self.encoder = None
        self.current_output = None
        self.current_file = None
        self.recording_thread = None
        self.continuous_recording = False

        # 통계
        self.recording_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.total_size = 0

        logger.info(f"[GPU-RECORDER] 카메라 {camera_id} GPU 녹화기 초기화")

    def _generate_filename(self):
        """파일명 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.save_dir / f"cam{self.camera_id}_{timestamp}.mp4"

    def _record_single_video(self, duration: int = None):
        """단일 비디오 녹화 (GPU 가속)"""
        # 설정에서 녹화 시간 가져오기
        if duration is None:
            duration = config_manager.get_segment_duration()

        start_time = datetime.now()
        start_str = start_time.strftime("%H:%M:%S")

        try:
            # 파일명 생성
            output_path = self._generate_filename()
            logger.info(f"[{start_str}] [CAM{self.camera_id}] GPU 녹화 시작: {output_path.name}")

            # 현재 파일 추적
            self.current_file = output_path

            # H.264 인코더 생성 (GPU 하드웨어 가속)
            # 설정에서 인코딩 파라미터 가져오기
            bitrate = config_manager.get_bitrate()
            framerate = config_manager.get_framerate()

            self.encoder = H264Encoder(
                bitrate=bitrate,    # 설정에서 가져온 비트레이트
                repeat=True,        # SPS/PPS 반복
                iperiod=framerate,  # I-프레임 주기 (프레임레이트와 동일)
                framerate=framerate # 설정에서 가져온 프레임레이트
            )

            # MP4 파일 출력 설정
            self.current_output = FfmpegOutput(str(output_path))
            self.encoder.output = self.current_output

            # 녹화 시작 (GPU 인코딩)
            self.picam2.start_encoder(self.encoder)
            self.is_recording = True

            # 지정된 시간 동안 녹화
            time.sleep(duration)

            # 녹화 중지
            self.picam2.stop_encoder(self.encoder)
            self.is_recording = False

            # 인코더 정리 (재사용 방지)
            self.encoder = None
            self.current_output = None

            # 파일 크기 확인
            if output_path.exists():
                file_size = output_path.stat().st_size
                size_mb = file_size / (1024 * 1024)
                end_time = datetime.now()
                end_str = end_time.strftime("%H:%M:%S")
                duration_actual = (end_time - start_time).total_seconds()

                logger.info(f"[{end_str}] [CAM{self.camera_id}] GPU 녹화 완료: {output_path.name} ({size_mb:.1f}MB, {duration_actual:.1f}초)")

                # 통계 업데이트
                self.success_count += 1
                self.total_size += file_size
                self.current_file = None
                return True
            else:
                logger.error(f"[CAM{self.camera_id}] 파일 생성 실패: {output_path.name}")
                self.fail_count += 1
                return False

        except Exception as e:
            logger.error(f"카메라 {self.camera_id} GPU 녹화 오류: {e}")
            self.is_recording = False
            self.fail_count += 1
            return False

    def start_continuous_recording(self, interval: int = None):
        """연속 녹화 시작 (30초 단위)"""
        # 설정에서 녹화 간격 가져오기
        if interval is None:
            interval = config_manager.get_segment_duration()

        if self.continuous_recording:
            logger.warning(f"[GPU-RECORDER] 카메라 {self.camera_id} 이미 연속 녹화 중 - 무시")
            return True  # 이미 실행 중이면 성공으로 처리

        logger.info(f"[GPU-RECORDER] 카메라 {self.camera_id} 연속 녹화 시작 요청")
        self.continuous_recording = True
        self.recording_thread = threading.Thread(
            target=self._continuous_recording_loop,
            args=(interval,),
            daemon=True
        )
        self.recording_thread.start()
        logger.info(f"[GPU-RECORDER] 카메라 {self.camera_id} 연속 녹화 시작 완료 ({interval}초 간격)")
        return True

    def _continuous_recording_loop(self, interval: int):
        """연속 녹화 루프 (스레드에서 실행)"""
        logger.info(f"[CAM{self.camera_id}] 연속 녹화 루프 시작")

        while self.continuous_recording:
            self.recording_count += 1

            # 녹화 실행
            success = self._record_single_video(interval)

            if success:
                logger.info(f"[CAM{self.camera_id}] 진행: 성공 {self.success_count}개 / 실패 {self.fail_count}개 / 총 {self.total_size/1024/1024:.1f}MB")
            else:
                logger.warning(f"[CAM{self.camera_id}] 실패: {self.recording_count}번째 녹화")
                # 실패해도 계속 진행 (중지하지 않음)

            # 다음 녹화를 위한 대기
            if self.continuous_recording:
                logger.info(f"[CAM{self.camera_id}] 다음 녹화까지 0.5초 대기 중...")
                time.sleep(0.5)
                logger.info(f"[CAM{self.camera_id}] 연속 녹화 상태 확인: {self.continuous_recording}")

        logger.info(f"[CAM{self.camera_id}] 연속 녹화 루프 종료 (continuous_recording = {self.continuous_recording})")

    def stop_recording(self):
        """녹화 중지"""
        self.continuous_recording = False

        # 현재 녹화 중이면 중지
        if self.is_recording and self.encoder:
            try:
                self.picam2.stop_encoder(self.encoder)
                self.is_recording = False
                self.encoder = None  # 인코더 정리
                self.current_output = None
                logger.info(f"[GPU-RECORDER] 카메라 {self.camera_id} 녹화 중지")
            except Exception as e:
                # 이미 중지된 경우 무시
                if "already stopped" not in str(e).lower():
                    logger.error(f"녹화 중지 오류: {e}")
                self.is_recording = False
                self.encoder = None
                self.current_output = None

        # 스레드 종료 대기
        if self.recording_thread:
            self.recording_thread.join(timeout=2)

        # 미완성 파일 처리
        if self.current_file and self.current_file.exists():
            try:
                file_size = self.current_file.stat().st_size
                if file_size < 10240:  # 10KB 미만 파일은 삭제
                    self.current_file.unlink()
                    logger.info(f"[CAM{self.camera_id}] 손상된 파일 삭제: {self.current_file.name}")
                else:
                    logger.info(f"[CAM{self.camera_id}] 마지막 파일 보존: {self.current_file.name} ({file_size/1024/1024:.1f}MB)")
            except Exception as e:
                logger.error(f"파일 처리 오류: {e}")


class CameraManager:
    """카메라 관리 핵심 클래스 (보호 대상)"""
    
    def __init__(self):
        self.current_camera = 0
        # 설정에서 기본 해상도 가져오기
        default_quality = config_manager.get('streaming.default_quality', '640x480')
        self.current_resolution = default_quality
        self.camera_instances = {}
        self.active_clients: Set[str] = set()
        self.dual_mode = False  # 듀얼 카메라 모드 플래그
        self.is_recording = False  # 녹화 상태 플래그 (리소스 경합 방지용)

        # 연속 녹화 시스템
        self.recording_enabled = False
        self.recording_threads = {}
        
        # 해상도 설정
        # 설정에서 해상도 및 최대 클라이언트 수 가져오기
        resolution = config_manager.get_resolution()
        max_clients = config_manager.get_max_clients()

        self.RESOLUTIONS = {
            "640x480": {"width": 640, "height": 480, "name": "480p", "max_clients": max_clients},
            "1280x720": {"width": 1280, "height": 720, "name": "720p", "max_clients": max_clients}
        }
        
        # 녹화 시스템
        self.recorders = {}

        # 통계 정보
        self.stream_stats = {
            0: {"frame_count": 0, "avg_frame_size": 0, "fps": 0, "last_update": 0, "recording": False},
            1: {"frame_count": 0, "avg_frame_size": 0, "fps": 0, "last_update": 0, "recording": False}
        }
        
        # 직접 캡처 방식으로 변경 - 버퍼 시스템 제거
    
    def get_max_clients(self) -> int:
        """현재 해상도에 따른 최대 클라이언트 수"""
        return self.RESOLUTIONS.get(self.current_resolution, {}).get("max_clients", 1)
    
    def can_accept_client(self, client_ip: str) -> bool:
        """클라이언트 접속 가능 여부 확인"""
        max_clients = self.get_max_clients()
        return len(self.active_clients) < max_clients or client_ip in self.active_clients
    
    def is_camera_active(self) -> bool:
        """카메라 활성 상태 확인"""
        return self.current_camera in self.camera_instances
    
    def ensure_camera_started(self) -> bool:
        """카메라 시작 보장"""
        if self.current_camera not in self.camera_instances:
            return self.start_camera_stream(self.current_camera)
        return True
    
    def start_camera_stream(self, camera_id: int, resolution: str = None) -> bool:
        """카메라 스트리밍 시작 - GPU 버전"""
        logger.info(f"[START] 카메라 {camera_id} 스트리밍 시작 요청 (해상도: {resolution or self.current_resolution})")

        # 기존 카메라 인스턴스가 있으면 재사용 (연속 녹화 유지)
        if camera_id in self.camera_instances:
            logger.info(f"기존 카메라 {camera_id} 인스턴스 재사용 (녹화 유지)")
            return True
        
        # 해상도 설정
        if resolution is None:
            resolution = self.current_resolution
        
        res_config = self.RESOLUTIONS.get(resolution, self.RESOLUTIONS["640x480"])
        width = res_config["width"]
        height = res_config["height"]
        
        try:
            # Picamera2 인스턴스 생성
            picam2 = Picamera2(camera_num=camera_id)
            
            # Pi5 듀얼 스트림 최적화 설정
            # 메인: H.264 녹화 우선, 서브: MJPEG 스트리밍
            config = picam2.create_video_configuration(
                main={
                    "size": (width, height),
                    "format": "YUV420"  # H.264 녹화 최적화 (GPU 가속)
                },
                lores={
                    "size": (width, height),  # 스트리밍도 동일 해상도 유지
                    "format": "RGB888"        # MJPEG 스트리밍 최적화
                },
                buffer_count=2,  # 버퍼 수 감소로 리소스 분산
                queue=False,     # 레이턴시 최소화
                transform=libcamera.Transform(hflip=True)  # 좌우 반전 (거울모드)
            )

            picam2.configure(config)
            picam2.start()
            
            self.camera_instances[camera_id] = picam2

            # 녹화기 초기화 (GPU 레코더 사용)
            if camera_id not in self.recorders:
                self.recorders[camera_id] = GPURecorder(camera_id, picam2)

            logger.info(f"[OK] Picamera2 카메라 {camera_id} 시작됨 ({width}x{height})")

            # 녹화는 나중에 enable_recording()에서 일괄 시작
            # (듀얼 모드 시 타이밍 이슈 방지)

            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 카메라 {camera_id} 시작 실패: {e}")
            if camera_id in self.camera_instances:
                del self.camera_instances[camera_id]
            return False
    
    def stop_camera_stream(self, camera_id: int):
        """카메라 스트리밍 중지 - 연속 녹화는 유지"""
        # 연속 녹화는 중지하지 않음 (24시간 연속 녹화 유지)
        # 듀얼 모드에서는 카메라 인스턴스를 유지하고 스트리밍만 중지

        # 듀얼 모드인 경우 카메라 인스턴스 유지 (녹화 지속을 위해)
        if self.dual_mode and camera_id in self.camera_instances:
            logger.info(f"[DUAL-MODE] 카메라 {camera_id} 스트리밍 중지 (녹화 유지)")
            # 통계만 초기화, 카메라 인스턴스는 유지
            self.stream_stats[camera_id] = {
                "frame_count": 0,
                "avg_frame_size": 0,
                "fps": 0,
                "last_update": 0,
                "recording": camera_id in self.recorders and self.recorders[camera_id].continuous_recording
            }
            return

        # 싱글 모드로 전환 시에만 카메라 완전 중지
        if camera_id in self.camera_instances:
            try:
                logger.info(f"[STOP] 카메라 {camera_id} 완전 중지 중...")
                picam2 = self.camera_instances[camera_id]
                picam2.stop()
                picam2.close()
                del self.camera_instances[camera_id]

                # 통계 초기화
                self.stream_stats[camera_id] = {
                    "frame_count": 0,
                    "avg_frame_size": 0,
                    "fps": 0,
                    "last_update": 0,
                    "recording": False
                }

                # 클라이언트 목록 클리어
                self.active_clients.clear()

                logger.info(f"[OK] 카메라 {camera_id} 완전 중지됨")
            except Exception as e:
                logger.error(f"[ERROR] 카메라 {camera_id} 중지 실패: {e}")
    
    # 직접 캡처 방식
    
    def generate_stream(self, client_ip: str, camera_id: int = None):
        """MJPEG 스트림 생성 - 원본과 동일한 직접 캡처 방식"""
        logger.info(f"[STREAM] 클라이언트 연결: {client_ip}")
        self.active_clients.add(client_ip)
        
        # 카메라 인스턴스 가져오기
        target_camera = camera_id if camera_id is not None else self.current_camera
        picam2 = self.camera_instances.get(target_camera)
        if not picam2:
            logger.error(f"[ERROR] 카메라 {target_camera} 인스턴스 없음")
            return

        # 녹화기 가져오기
        recorder = self.recorders.get(target_camera)
        
        # 통계 변수
        frame_count = 0
        total_frame_size = 0
        start_time = time.time()
        last_fps_update = start_time
        
        # 해상도별 설정
        is_720p = self.current_resolution == "1280x720"
        frame_min_size = 5000 if is_720p else 2000
        frame_max_size = 500000 if is_720p else 200000
        
        try:
            while True:
                try:
                    # 카메라가 중지되었는지 확인
                    if target_camera not in self.camera_instances:
                        logger.info(f"[STREAM] 카메라 {target_camera} 중지됨, 스트림 종료")
                        break
                    
                    # Picamera2 lores 스트림에서 RGB 배열 캡처 후 JPEG 변환 (스트리밍 전용)
                    rgb_array = picam2.capture_array('lores')  # lores 스트림에서 RGB 배열 캡처

                    # RGB를 JPEG로 인코딩
                    success, frame_data = cv2.imencode('.jpg', rgb_array, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not success:
                        continue
                    frame_data = frame_data.tobytes()
                    
                    if not frame_data:
                        logger.warning(f"[WARN] 카메라 {target_camera}에서 데이터 없음")
                        break
                    
                    frame_size = len(frame_data)

                    # GPU 녹화기는 별도 스레드에서 자동으로 처리됨
                    # (프레임 전달 불필요)

                    # 프레임 크기 검증 (원본과 동일)
                    if frame_min_size < frame_size < frame_max_size:
                        try:
                            yield b'--frame\r\n'
                            yield b'Content-Type: image/jpeg\r\n'
                            yield f'Content-Length: {frame_size}\r\n\r\n'.encode()
                            yield frame_data
                            yield b'\r\n'
                            
                            # 통계 업데이트
                            frame_count += 1
                            total_frame_size += frame_size
                            
                            # 프레임 카운터 자동 리셋 (10만 프레임마다 = 약 55분)
                            if frame_count >= 100000:
                                logger.info(f"[RESET] Auto-reset: Frame counter reached 100K, resetting for memory stability")
                                frame_count = 1  # 나누기 오류 방지를 위해 1로 설정
                                total_frame_size = frame_size
                                start_time = time.time()
                                last_fps_update = start_time
                                # 통계 초기화
                                self.stream_stats[self.current_camera] = {
                                    "frame_count": 1,
                                    "avg_frame_size": frame_size,
                                    "fps": 30.0,
                                    "last_update": start_time,
                                    "recording": recorder.is_recording if recorder else False
                                }
                            
                        except Exception as stream_error:
                            logger.error(f"[ERROR] 스트림 전송 오류: {stream_error}")
                            break
                    
                    # FPS 통계 업데이트 (1초마다)
                    current_time = time.time()
                    if current_time - last_fps_update >= 1.0:
                        elapsed = current_time - start_time
                        fps = frame_count / elapsed if elapsed > 0 else 0
                        avg_size = total_frame_size / frame_count if frame_count > 0 else 0
                        
                        # 누적 프레임 수 계산 (100K 리셋 고려)
                        if frame_count == 1:
                            # 리셋된 경우: 새로 시작
                            cumulative_frames = 1
                        else:
                            # 정상 증가: 기존 값에서 1씩 증가
                            cumulative_frames = self.stream_stats[self.current_camera]["frame_count"] + 1
                        
                        self.stream_stats[self.current_camera] = {
                            "frame_count": cumulative_frames,
                            "avg_frame_size": avg_size,
                            "fps": round(fps, 1),
                            "last_update": current_time,
                            "recording": recorder.is_recording if recorder else False
                        }
                        
                        last_fps_update = current_time
                    
                except Exception as capture_error:
                    logger.error(f"[ERROR] 캡처 오류: {capture_error}")
                    time.sleep(0.1)  # 오류 시 잠시 대기
                    
        except Exception as e:
            logger.error(f"[ERROR] 스트림 오류: {e}")
        finally:
            self.active_clients.discard(client_ip)
            logger.info(f"[STREAM] 클라이언트 연결 해제: {client_ip}")
    
    async def switch_camera(self, camera_id: int) -> bool:
        """카메라 전환"""
        if camera_id == self.current_camera:
            return True
        
        logger.info(f"[SWITCH] 카메라 {self.current_camera} → {camera_id}")
        
        # 기존 카메라 정지
        self.stop_camera_stream(self.current_camera)
        await asyncio.sleep(0.5)
        
        # 새 카메라 시작
        success = self.start_camera_stream(camera_id)
        
        if success:
            self.current_camera = camera_id
            logger.info(f"[OK] 카메라 {camera_id}로 전환 완료")
            return True
        else:
            # 실패 시 기존 카메라 다시 시작
            self.start_camera_stream(self.current_camera)
            return False
    
    async def change_resolution(self, resolution: str) -> bool:
        """해상도 변경"""
        if resolution not in self.RESOLUTIONS:
            return False
        
        if resolution == self.current_resolution:
            return True
        
        logger.info(f"[RESOLUTION] {self.current_resolution} → {resolution}")
        
        old_resolution = self.current_resolution
        self.current_resolution = resolution
        
        # 현재 스트리밍 중인 카메라가 있으면 재시작
        if self.current_camera in self.camera_instances:
            self.stop_camera_stream(self.current_camera)
            await asyncio.sleep(2.0)
            
            success = self.start_camera_stream(self.current_camera, resolution)
            
            if success:
                await asyncio.sleep(1.0)
                logger.info(f"[OK] 해상도 변경 완료: {resolution}")
                return True
            else:
                logger.error(f"[ERROR] 해상도 변경 실패, 복구 중...")
                self.current_resolution = old_resolution
                await asyncio.sleep(1.0)
                self.start_camera_stream(self.current_camera, old_resolution)
                return False
        
        return True
    
    def start_continuous_recording(self, camera_id: int, interval: int = None):
        """GPU 가속 연속 녹화 시작"""
        # 설정에서 녹화 간격 가져오기
        if interval is None:
            interval = config_manager.get_segment_duration()

        if camera_id not in self.recorders:
            logger.error(f"[ERROR] 카메라 {camera_id} 레코더 없음")
            return

        # GPU 레코더의 연속 녹화 시작
        recorder = self.recorders[camera_id]
        recorder.start_continuous_recording(interval)

        # 통계 업데이트
        self.stream_stats[camera_id]["recording"] = True
        self.recording_threads[camera_id] = True

        logger.info(f"[GPU-RECORDING] 카메라 {camera_id} GPU 연속 녹화 시작 ({interval}초 간격)")

    def enable_recording(self):
        """모든 활성 카메라에 대해 GPU 녹화 활성화"""
        self.recording_enabled = True
        active_cameras = list(self.camera_instances.keys())

        for camera_id in active_cameras:
            self.start_continuous_recording(camera_id)
            logger.info(f"[GPU-RECORDING] 카메라 {camera_id} 연속 녹화 시작")

        logger.info(f"[GPU-RECORDING] 녹화 기능 활성화 완료 (활성 카메라: {active_cameras})")

    def disable_recording(self):
        """모든 녹화 비활성화"""
        self.recording_enabled = False
        for camera_id in self.recording_threads.keys():
            self.recording_threads[camera_id] = False

        # GPU 레코더 중지
        for camera_id, recorder in self.recorders.items():
            recorder.stop_recording()
            self.stream_stats[camera_id]["recording"] = False

        logger.info("[GPU-RECORDING] 모든 GPU 녹화 비활성화")

    def start_single_recording(self, camera_id: int, duration: int = None):
        """단일 GPU 녹화 (웹 UI용)"""
        # 설정에서 녹화 시간 가져오기
        if duration is None:
            duration = config_manager.get_segment_duration()

        if camera_id not in self.recorders:
            logger.error(f"[ERROR] 카메라 {camera_id} 레코더 없음")
            return False

        recorder = self.recorders[camera_id]
        if recorder.is_recording or recorder.continuous_recording:
            logger.warning(f"[GPU-RECORDER] 카메라 {camera_id} 이미 녹화 중")
            return False

        # 단일 녹화 실행
        success = recorder._record_single_video(duration)
        logger.info(f"[GPU-RECORDING] 카메라 {camera_id} 단일 녹화 {'성공' if success else '실패'} ({duration}초)")
        return success

    def stop_single_recording(self, camera_id: int):
        """단일 녹화 중지 (웹 UI용)"""
        if camera_id not in self.recorders:
            return False

        self.recorders[camera_id].stop_recording()
        logger.info(f"[RECORDING] 카메라 {camera_id} 단일 녹화 중지")
        return True

    def is_recording(self, camera_id: int = None) -> bool:
        """녹화 상태 확인"""
        if camera_id is None:
            camera_id = self.current_camera

        if camera_id not in self.recorders:
            return False

        return self.recorders[camera_id].is_recording

    def get_stats(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        return {
            "current_camera": self.current_camera,
            "resolution": self.current_resolution,
            "codec": "MJPEG",
            "quality": "80-85%",
            "engine": "Picamera2",
            "active_clients": len(self.active_clients),
            "max_clients": self.get_max_clients(),
            "recording_enabled": self.recording_enabled,
            "stats": self.stream_stats[self.current_camera]
        }
    
    def enable_dual_mode(self) -> bool:
        """듀얼 카메라 모드 활성화 - 두 카메라 동시 녹화"""
        logger.info("[DUAL] 듀얼 카메라 모드 활성화 중...")

        # 카메라 0 시작
        success_cam0 = self.start_camera_stream(0, self.current_resolution)
        if not success_cam0:
            logger.error("[DUAL] 카메라 0 시작 실패")
            return False

        # 잠시 대기 (카메라 초기화 시간)
        time.sleep(0.5)

        # 카메라 1 시작
        success_cam1 = self.start_camera_stream(1, self.current_resolution)
        if not success_cam1:
            logger.error("[DUAL] 카메라 1 시작 실패")
            # 카메라 0도 정리
            self.stop_camera_stream(0)
            return False

        self.dual_mode = True
        logger.info("[DUAL] 듀얼 카메라 모드 활성화 완료 (cam0, cam1 모두 활성)")

        # 두 카메라 모두 활성화됨을 확인
        logger.info(f"[DUAL] 활성 카메라: {list(self.camera_instances.keys())}")
        logger.info(f"[DUAL] 활성 녹화기: {list(self.recorders.keys())}")

        return True
    
    def disable_dual_mode(self):
        """듀얼 카메라 모드 비활성화 - 연속 녹화는 유지"""
        logger.info("[DUAL] 듀얼 카메라 모드 비활성화 중... (연속 녹화 유지)")

        # 듀얼 모드 플래그 비활성화
        self.dual_mode = False

        # 연속 녹화는 중지하지 않음 - 카메라 인스턴스는 유지
        # 스트리밍 뷰만 싱글 모드로 전환
        # 모든 카메라는 백그라운드에서 녹화 계속 진행

        logger.info("[DUAL] 듀얼 카메라 모드 비활성화 완료 (모든 카메라 녹화 유지)")
    
    async def shutdown(self):
        """시스템 종료"""
        # 녹화 중지
        self.disable_recording()

        # 카메라 종료
        for camera_id in list(self.camera_instances.keys()):
            logger.info(f"[SHUTDOWN] 카메라 {camera_id} 중지 중...")
            self.stop_camera_stream(camera_id)
        logger.info("[SHUTDOWN] 모든 카메라 중지 완료")


def main():
    """메인 함수"""
    logger.info("[INIT] SHT CCTV 시스템 시작")
    
    # 카메라 관리자 생성 (핵심 로직)
    camera_manager = CameraManager()
    
    # 커스텀 시그널 핸들러 - 즉시 종료
    def shutdown_handler(sig, _frame):
        logger.info(f"\n[SIGNAL] Received signal {sig} - Immediate shutdown")
        logger.info("[SHUTDOWN] 시스템 정리 중...")

        # 녹화 중지
        camera_manager.disable_recording()

        # 카메라 정리 (동기적으로 처리)
        for camera_id in list(camera_manager.camera_instances.keys()):
            camera_manager.stop_camera_stream(camera_id)

        logger.info("[SHUTDOWN] 모든 카메라 중지 완료")

        # 즉시 강제 종료
        import os
        os._exit(0)
    
    # SIGINT 핸들러만 설정 (Ctrl+C용)
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    # 웹 API 생성 (공개 인터페이스)
    web_api = CCTVWebAPI(camera_manager)
    
    # 종료 시 클린업
    def cleanup():
        logger.info("[CLEANUP] 시스템 종료 중...")
        camera_manager.disable_recording()
        for camera_id in list(camera_manager.camera_instances.keys()):
            camera_manager.stop_camera_stream(camera_id)
    
    atexit.register(cleanup)
    
    # 듀얼 카메라 모드 시작 (두 카메라 동시 녹화)
    success = camera_manager.enable_dual_mode()

    if not success:
        # 듀얼 모드 실패 시 카메라 0만 시작
        logger.warning("[INIT] 듀얼 모드 실패, 카메라 0만 시작")
        camera_manager.start_camera_stream(0)

    # GPU 가속 연속 녹화 활성화 (모든 활성 카메라에 대해)
    camera_manager.enable_recording()  # GPU 자동 연속 녹화 시작
    
    # 서버 실행 - 시그널 핸들링 제어
    try:
        # uvicorn 서버 설정
        config = uvicorn.Config(
            web_api.app,
            host="0.0.0.0",
            port=config_manager.get_web_port(),
            log_level="info"
        )
        server = uvicorn.Server(config)
        
        # uvicorn의 install_signal_handlers 메서드 오버라이드
        server.install_signal_handlers = lambda: None
        
        # 우리의 시그널 핸들러 설정
        signal.signal(signal.SIGINT, shutdown_handler) 
        signal.signal(signal.SIGTERM, shutdown_handler)
        
        # 서버 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())
        
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass  # 시그널 핸들러에서 처리됨
    except Exception as e:
        logger.error(f"[ERROR] Server error: {e}")
    finally:
        pass  # cleanup은 시그널 핸들러에서 처리됨


if __name__ == "__main__":
    main()