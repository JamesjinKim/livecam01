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
import queue
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Set
import logging
import uvicorn

# Picamera2 imports
try:
    from picamera2 import Picamera2
    import libcamera
except ImportError as e:
    print(f"[ERROR] Picamera2 not installed: {e}")
    print("[INSTALL] Run: sudo apt install -y python3-picamera2")
    sys.exit(1)

# 웹 API 임포트
from web.api import CCTVWebAPI

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FrameRecorder:
    """프레임 기반 녹화 클래스 - 스트리밍 중단 없이 녹화"""

    def __init__(self, camera_id: int, save_dir: str = None):
        self.camera_id = camera_id
        self.save_dir = Path(save_dir or f"videos/cam{camera_id}")
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # 녹화 상태
        self.is_recording = False
        self.frame_queue = queue.Queue(maxsize=900)  # 30초 버퍼 (30fps)
        self.recording_thread = None
        self.video_writer = None

        logger.info(f"[RECORDER] 카메라 {camera_id} 녹화기 초기화")

    def add_frame(self, frame_data: bytes):
        """프레임 추가 (JPEG 바이트)"""
        if not self.is_recording:
            return

        try:
            # 큐가 가득 차면 오래된 프레임 제거
            if self.frame_queue.full():
                self.frame_queue.get_nowait()

            self.frame_queue.put_nowait(frame_data)
        except queue.Full:
            pass

    def start_recording(self, duration: int = 30):
        """녹화 시작"""
        if self.is_recording:
            logger.warning(f"[RECORDER] 카메라 {self.camera_id} 이미 녹화 중")
            return False

        self.is_recording = True
        self.recording_thread = threading.Thread(
            target=self._record_video,
            args=(duration,),
            daemon=True
        )
        self.recording_thread.start()
        logger.info(f"[RECORDER] 카메라 {self.camera_id} 녹화 시작 ({duration}초)")
        return True

    def stop_recording(self):
        """녹화 중지"""
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.join(timeout=2)
        logger.info(f"[RECORDER] 카메라 {self.camera_id} 녹화 중지")

    def _record_video(self, duration: int):
        """비디오 녹화 스레드"""
        # 날짜별 폴더 생성
        date_folder = self.save_dir / datetime.now().strftime("%y%m%d")
        date_folder.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = date_folder / f"cam{self.camera_id}_{timestamp}.mp4"

        try:
            # OpenCV VideoWriter 설정
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = 30.0
            frame_size = (640, 480)

            writer = cv2.VideoWriter(
                str(output_path),
                fourcc,
                fps,
                frame_size
            )

            if not writer.isOpened():
                logger.error(f"[RECORDER] VideoWriter 열기 실패")
                return

            start_time = time.time()
            frame_count = 0

            logger.info(f"[RECORDER] 녹화 시작: {output_path.name}")

            # 지정된 시간 동안 녹화
            while self.is_recording and (time.time() - start_time) < duration:
                try:
                    # 큐에서 JPEG 프레임 가져오기
                    frame_data = self.frame_queue.get(timeout=0.1)

                    # JPEG를 OpenCV 형식으로 변환
                    nparr = np.frombuffer(frame_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if frame is not None:
                        # 필요시 크기 조정
                        if frame.shape[:2] != (frame_size[1], frame_size[0]):
                            frame = cv2.resize(frame, frame_size)

                        writer.write(frame)
                        frame_count += 1

                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"[RECORDER] 프레임 처리 오류: {e}")

            # 녹화 완료
            writer.release()

            # 파일 정보 출력
            if output_path.exists():
                file_size = output_path.stat().st_size / (1024 * 1024)
                actual_duration = time.time() - start_time
                logger.info(f"[RECORDER] 녹화 완료: {output_path.name}")
                logger.info(f"           크기: {file_size:.1f}MB, 시간: {actual_duration:.1f}초, 프레임: {frame_count}")

        except Exception as e:
            logger.error(f"[RECORDER] 녹화 오류: {e}")
        finally:
            self.is_recording = False


class CameraManager:
    """카메라 관리 핵심 클래스 (보호 대상)"""
    
    def __init__(self):
        self.current_camera = 0
        self.current_resolution = "640x480"
        self.camera_instances = {}
        self.active_clients: Set[str] = set()
        self.dual_mode = False  # 듀얼 카메라 모드 플래그
        self.is_recording = False  # 녹화 상태 플래그 (리소스 경합 방지용)

        # 연속 녹화 시스템
        self.recording_enabled = False
        self.recording_threads = {}
        
        # 해상도 설정
        self.RESOLUTIONS = {
            "640x480": {"width": 640, "height": 480, "name": "480p", "max_clients": 2},
            "1280x720": {"width": 1280, "height": 720, "name": "720p", "max_clients": 2}
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
        
        if camera_id in self.camera_instances:
            logger.info(f"기존 카메라 {camera_id} 인스턴스 종료 중...")
            self.stop_camera_stream(camera_id)
        
        # 해상도 설정
        if resolution is None:
            resolution = self.current_resolution
        
        res_config = self.RESOLUTIONS.get(resolution, self.RESOLUTIONS["640x480"])
        width = res_config["width"]
        height = res_config["height"]
        
        try:
            # Picamera2 인스턴스 생성
            picam2 = Picamera2(camera_num=camera_id)
            
            # Pi5 최적화 설정 - ISP 리소스 경합 해결
            # 카메라별 다른 포맷 사용으로 색상 문제 방지
            config = picam2.create_video_configuration(
                main={
                    "size": (width, height),
                    "format": "RGB888" if camera_id == 0 else "YUV420"  # 카메라별 다른 포맷으로 ISP 경합 방지
                },
                buffer_count=2,  # 버퍼 수 감소로 리소스 분산 (4->2)
                queue=False,     # 레이턴시 최소화
                transform=libcamera.Transform(hflip=True)  # 좌우 반전 (거울모드)
            )

            picam2.configure(config)
            picam2.start()
            
            self.camera_instances[camera_id] = picam2

            # 녹화기 초기화
            if camera_id not in self.recorders:
                self.recorders[camera_id] = FrameRecorder(camera_id)

            logger.info(f"[OK] Picamera2 카메라 {camera_id} 시작됨 ({width}x{height})")

            # 녹화가 활성화된 경우 자동 시작
            if self.recording_enabled:
                self.start_continuous_recording(camera_id)

            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 카메라 {camera_id} 시작 실패: {e}")
            if camera_id in self.camera_instances:
                del self.camera_instances[camera_id]
            return False
    
    def stop_camera_stream(self, camera_id: int):
        """카메라 스트리밍 중지"""
        # 녹화 중지
        if camera_id in self.recorders:
            self.recorders[camera_id].stop_recording()

        # 연속 녹화 스레드 종료
        if camera_id in self.recording_threads:
            self.recording_threads[camera_id] = False

        if camera_id in self.camera_instances:
            try:
                logger.info(f"[STOP] 카메라 {camera_id} 중지 중...")
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
                
                logger.info(f"[OK] 카메라 {camera_id} 중지됨")
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
                    
                    # Picamera2로 직접 JPEG 프레임 캡처 (원본과 동일)
                    import io
                    stream = io.BytesIO()
                    picam2.capture_file(stream, format='jpeg')
                    frame_data = stream.getvalue()
                    stream.close()
                    
                    if not frame_data:
                        logger.warning(f"[WARN] 카메라 {target_camera}에서 데이터 없음")
                        break
                    
                    frame_size = len(frame_data)

                    # 녹화기에 프레임 전달 (비동기)
                    if recorder and recorder.is_recording:
                        recorder.add_frame(frame_data)

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
    
    def start_continuous_recording(self, camera_id: int, interval: int = 30):
        """연속 녹화 시작"""
        if camera_id not in self.recorders:
            logger.error(f"[ERROR] 카메라 {camera_id} 레코더 없음")
            return

        def continuous_record():
            self.recording_threads[camera_id] = True
            while self.recording_threads.get(camera_id, False):
                recorder = self.recorders[camera_id]
                recorder.start_recording(duration=interval)

                # 통계 업데이트
                self.stream_stats[camera_id]["recording"] = True

                # 녹화 완료 대기
                time.sleep(interval + 1)

            self.stream_stats[camera_id]["recording"] = False

        thread = threading.Thread(target=continuous_record, daemon=True)
        thread.start()
        logger.info(f"[RECORDING] 카메라 {camera_id} 연속 녹화 시작 ({interval}초 간격)")

    def enable_recording(self):
        """모든 활성 카메라에 대해 녹화 활성화"""
        self.recording_enabled = True
        for camera_id in self.camera_instances.keys():
            self.start_continuous_recording(camera_id)
        logger.info("[RECORDING] 녹화 기능 활성화")

    def disable_recording(self):
        """모든 녹화 비활성화"""
        self.recording_enabled = False
        for camera_id in self.recording_threads.keys():
            self.recording_threads[camera_id] = False
        for recorder in self.recorders.values():
            recorder.stop_recording()
        logger.info("[RECORDING] 녹화 기능 비활성화")

    def start_single_recording(self, camera_id: int, duration: int = 30):
        """30초 단위 녹화 (웹 UI용)"""
        if camera_id not in self.recorders:
            logger.error(f"[ERROR] 카메라 {camera_id} 레코더 없음")
            return False

        if self.recorders[camera_id].is_recording:
            logger.warning(f"[RECORDER] 카메라 {camera_id} 이미 녹화 중")
            return False

        self.recorders[camera_id].start_recording(duration=duration)
        logger.info(f"[RECORDING] 카메라 {camera_id} 단일 녹화 시작 ({duration}초)")
        return True

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
        """듀얼 카메라 모드 활성화"""
        logger.info("[DUAL] 듀얼 카메라 모드 활성화 중...")
        
        # 두 카메라 모두 시작
        success_cam0 = self.start_camera_stream(0, self.current_resolution)
        success_cam1 = self.start_camera_stream(1, self.current_resolution)
        
        if success_cam0 and success_cam1:
            self.dual_mode = True
            logger.info("[DUAL] 듀얼 카메라 모드 활성화 완료")
            return True
        else:
            # 실패 시 정리
            if 0 in self.camera_instances:
                self.stop_camera_stream(0)
            if 1 in self.camera_instances:
                self.stop_camera_stream(1)
            self.dual_mode = False
            logger.error("[DUAL] 듀얼 카메라 모드 활성화 실패")
            return False
    
    def disable_dual_mode(self):
        """듀얼 카메라 모드 비활성화"""
        logger.info("[DUAL] 듀얼 카메라 모드 비활성화 중...")
        
        # 현재 카메라가 아닌 카메라 정지
        other_camera = 1 if self.current_camera == 0 else 0
        if other_camera in self.camera_instances:
            self.stop_camera_stream(other_camera)
        
        self.dual_mode = False
        logger.info("[DUAL] 듀얼 카메라 모드 비활성화 완료")
    
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
    
    # 기본 카메라 시작 중요한 부분임
    camera_manager.start_camera_stream(0)

    #중요한 부분임 녹화 기능 활성화 (선택적)
    #camera_manager.enable_recording()  # 자동 연속 녹화를 원할 경우 주석 해제
    
    # 서버 실행 - 시그널 핸들링 제어
    try:
        # uvicorn 서버 설정
        config = uvicorn.Config(
            web_api.app,
            host="0.0.0.0",
            port=8001,
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