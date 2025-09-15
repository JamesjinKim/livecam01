#!/usr/bin/env python3
"""
Picamera2 기반 CCTV 시스템 - 분리된 버전
핵심 카메라 로직과 웹 인터페이스 분리
"""

import asyncio
import signal
import sys
import time
import threading
import atexit
from typing import Optional, Dict, Any, Set
from collections import deque
import logging
import uvicorn

# Picamera2 imports
try:
    from picamera2 import Picamera2
    from libcamera import Transform
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

class CameraManager:
    """카메라 관리 핵심 클래스 (보호 대상)"""
    
    def __init__(self):
        self.current_camera = 0
        self.current_resolution = "640x480"
        self.camera_instances = {}
        self.active_clients: Set[str] = set()
        self.dual_mode = False  # 듀얼 카메라 모드 플래그
        
        # 해상도 설정
        self.RESOLUTIONS = {
            "640x480": {"width": 640, "height": 480, "name": "480p", "max_clients": 2},
            "1280x720": {"width": 1280, "height": 720, "name": "720p", "max_clients": 2}
        }
        
        # 통계 정보
        self.stream_stats = {
            0: {"frame_count": 0, "avg_frame_size": 0, "fps": 0, "last_update": 0},
            1: {"frame_count": 0, "avg_frame_size": 0, "fps": 0, "last_update": 0}
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
            
            # Pi5 최적화 설정 (좌우 반전 포함) - ISP 리소스 경합 해결
            # 카메라별 다른 포맷 사용으로 색상 문제 방지
            config = picam2.create_video_configuration(
                main={
                    "size": (width, height),
                    "format": "RGB888" if camera_id == 0 else "YUV420"  # 카메라별 다른 포맷으로 ISP 경합 방지
                },
                transform=libcamera.Transform(hflip=True),  # 좌우 반전 (거울 모드)
                buffer_count=2,  # 버퍼 수 감소로 리소스 분산 (4->2)
                queue=False      # 레이턴시 최소화
            )
            
            picam2.configure(config)
            picam2.start()
            
            self.camera_instances[camera_id] = picam2
            logger.info(f"[OK] Picamera2 카메라 {camera_id} 시작됨 ({width}x{height})")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] 카메라 {camera_id} 시작 실패: {e}")
            if camera_id in self.camera_instances:
                del self.camera_instances[camera_id]
            return False
    
    def stop_camera_stream(self, camera_id: int):
        """카메라 스트리밍 중지"""
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
                    "last_update": 0
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
                                    "last_update": start_time
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
                            "last_update": current_time
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
        for camera_id in list(self.camera_instances.keys()):
            logger.info(f"[SHUTDOWN] 카메라 {camera_id} 중지 중...")
            self.stop_camera_stream(camera_id)
        logger.info("[SHUTDOWN] 모든 카메라 중지 완료")


def main():
    """메인 함수"""
    logger.info("[INIT] SHT CCTV 시스템 시작")
    
    # 카메라 관리자 생성 (핵심 로직)
    camera_manager = CameraManager()
    
    # 원래 시그널 핸들러 저장
    original_sigint = signal.getsignal(signal.SIGINT)
    
    # 커스텀 시그널 핸들러 - 즉시 종료
    def shutdown_handler(sig, frame):
        logger.info(f"\n[SIGNAL] Received signal {sig} - Immediate shutdown")
        logger.info("[SHUTDOWN] 카메라 정리 중...")
        
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
        for camera_id in list(camera_manager.camera_instances.keys()):
            camera_manager.stop_camera_stream(camera_id)
    
    atexit.register(cleanup)
    
    # 기본 카메라 시작
    camera_manager.start_camera_stream(0)
    
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