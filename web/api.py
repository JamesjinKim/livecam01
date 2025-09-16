"""
FastAPI 라우터 모듈
웹 인터페이스와 API 엔드포인트 관리
"""

import asyncio
import subprocess
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
import logging

# uvicorn 서버
import os
import signal
import threading
import time

logger = logging.getLogger(__name__)

class CCTVWebAPI:
    """CCTV 웹 API 관리 클래스"""
    
    def __init__(self, camera_manager):
        """
        Args:
            camera_manager: 카메라 관리 객체 (핵심 로직)
        """
        self.app = FastAPI()
        self.camera_manager = camera_manager
        self.recording_processes = {}  # 녹화 프로세스 추적

        # 정적 파일 서빙 설정
        self.app.mount("/static", StaticFiles(directory="web/static"), name="static")

        # 라우트 설정
        self.setup_routes()
    
    def setup_routes(self):
        """라우트 설정"""
        
        @self.app.get("/")
        async def index():
            """메인 페이지"""
            return FileResponse("web/static/index.html")
        
        @self.app.post("/switch/{camera_id}")
        async def switch_camera(camera_id: int):
            """카메라 전환 (싱글 뷰로 전환)"""
            if camera_id not in [0, 1]:
                raise HTTPException(status_code=400, detail="Invalid camera ID")
            
            # 듀얼 모드 비활성화
            if self.camera_manager.dual_mode:
                self.camera_manager.disable_dual_mode()
            
            success = await self.camera_manager.switch_camera(camera_id)
            
            if success:
                return {"success": True, "message": f"Switched to camera {camera_id}", "dual_mode": False}
            else:
                raise HTTPException(status_code=500, detail="Failed to switch camera")
        
        @self.app.post("/api/dual_mode/{enable}")
        async def toggle_dual_mode(enable: bool):
            """듀얼 모드 토글"""
            if enable:
                success = self.camera_manager.enable_dual_mode()
                if success:
                    return {"success": True, "message": "Dual mode enabled", "dual_mode": True}
                else:
                    raise HTTPException(status_code=500, detail="Failed to enable dual mode")
            else:
                self.camera_manager.disable_dual_mode()
                return {"success": True, "message": "Dual mode disabled", "dual_mode": False}
        
        @self.app.api_route("/stream", methods=["GET", "HEAD"])
        async def video_stream(request: Request):
            """비디오 스트림 (현재 선택된 카메라)"""
            client_ip = request.client.host
            
            # HEAD 요청 처리 (하트비트 체크용)
            if request.method == "HEAD":
                if self.camera_manager.is_camera_active():
                    return Response(
                        status_code=200, 
                        headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
                    )
                else:
                    return Response(status_code=503, headers={"Content-Type": "text/plain"})
            
            # 클라이언트 제한 확인
            if not self.camera_manager.can_accept_client(client_ip):
                max_clients = self.camera_manager.get_max_clients()
                raise HTTPException(
                    status_code=423,
                    detail=f"Maximum {max_clients} client(s) allowed. Server at capacity."
                )
            
            # 스트림 시작
            if not self.camera_manager.ensure_camera_started():
                raise HTTPException(status_code=500, detail="Failed to start camera")
            
            return StreamingResponse(
                self.camera_manager.generate_stream(client_ip),
                media_type="multipart/x-mixed-replace; boundary=frame"
            )
        
        @self.app.api_route("/stream/{camera_id}", methods=["GET", "HEAD"])
        async def camera_stream(camera_id: int, request: Request):
            """특정 카메라 스트림 (듀얼 모드용)"""
            client_ip = request.client.host
            
            if camera_id not in [0, 1]:
                raise HTTPException(status_code=400, detail="Invalid camera ID")
            
            # HEAD 요청 처리
            if request.method == "HEAD":
                if camera_id in self.camera_manager.camera_instances:
                    return Response(
                        status_code=200,
                        headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
                    )
                else:
                    return Response(status_code=503, headers={"Content-Type": "text/plain"})
            
            # 듀얼 모드가 아닌 경우 활성화
            if not self.camera_manager.dual_mode:
                if not self.camera_manager.enable_dual_mode():
                    raise HTTPException(status_code=500, detail="Failed to enable dual mode")
            
            # 카메라가 활성화되어 있는지 확인
            if camera_id not in self.camera_manager.camera_instances:
                raise HTTPException(status_code=503, detail=f"Camera {camera_id} not active")
            
            return StreamingResponse(
                self.camera_manager.generate_stream(client_ip, camera_id),
                media_type="multipart/x-mixed-replace; boundary=frame"
            )
        
        @self.app.get("/api/stats")
        async def get_stream_stats():
            """스트리밍 통계 조회"""
            return self.camera_manager.get_stats()
        
        @self.app.post("/api/resolution/{resolution}")
        async def change_resolution(resolution: str):
            """해상도 변경"""
            success = await self.camera_manager.change_resolution(resolution)
            
            if success:
                return {"success": True, "message": f"Resolution changed to {resolution}"}
            else:
                raise HTTPException(status_code=500, detail="Failed to change resolution")
        
        @self.app.get("/exit")
        async def exit_system():
            """시스템 종료 페이지"""
            return FileResponse("web/static/exit.html")
        
        @self.app.post("/api/shutdown")
        async def shutdown_system():
            """시스템 안전 종료"""
            logger.info("[SHUTDOWN] System shutdown requested via web interface")
            
            # 카메라 관리자를 통해 종료
            await self.camera_manager.shutdown()
            #Uvicorn 서버 즉시 종료
            def force_shutdown():
                time.sleep(1)
                os._exit(0)  # 즉시 종료
            
            shutdown_thread = threading.Thread(target=force_shutdown)
            shutdown_thread.daemon = True
            shutdown_thread.start()
            
            return {"success": True, "message": "System shutting down"}

        @self.app.post("/api/recording/start/{camera_id}")
        async def start_recording(camera_id: int):
            """30초 녹화 시작 (스트리밍 중단 없이 프레임 공유 방식)"""
            if camera_id not in [0, 1]:
                raise HTTPException(status_code=400, detail="Invalid camera ID")

            # 카메라가 활성화되어 있는지 확인
            if camera_id not in self.camera_manager.camera_instances:
                raise HTTPException(status_code=404, detail=f"카메라 {camera_id} 비활성")

            # 녹화기 가져오기
            recorder = self.camera_manager.recorders.get(camera_id)
            if not recorder:
                raise HTTPException(status_code=500, detail=f"녹화기 초기화 실패")

            # 이미 녹화 중인지 확인
            if recorder.is_recording:
                return {
                    "success": False,
                    "message": f"카메라 {camera_id} 이미 녹화 중",
                    "camera_id": camera_id
                }

            try:
                # 30초 녹화 시작 (스트리밍 중단 없이)
                success = recorder.start_recording(duration=30)

                if success:
                    return {
                        "success": True,
                        "message": f"카메라 {camera_id} 녹화 시작 (30초)",
                        "camera_id": camera_id,
                        "duration": 30,
                        "note": "스트리밍 중단 없이 녹화 진행"
                    }
                else:
                    raise HTTPException(status_code=500, detail="녹화 시작 실패")

            except Exception as e:
                logger.error(f"[ERROR] 녹화 시작 오류: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

        @self.app.post("/api/recording/stop/{camera_id}")
        async def stop_recording(camera_id: int):
            """녹화 강제 중지"""
            if camera_id not in [0, 1]:
                raise HTTPException(status_code=400, detail="Invalid camera ID")

            # 녹화기 가져오기
            recorder = self.camera_manager.recorders.get(camera_id)
            if not recorder:
                raise HTTPException(status_code=404, detail=f"카메라 {camera_id} 녹화기 없음")

            if not recorder.is_recording:
                return {
                    "success": False,
                    "message": f"카메라 {camera_id} 녹화 중이 아님",
                    "camera_id": camera_id
                }

            try:
                recorder.stop_recording()

                return {
                    "success": True,
                    "message": f"카메라 {camera_id} 녹화 중지",
                    "camera_id": camera_id
                }

            except Exception as e:
                logger.error(f"[ERROR] 녹화 중지 실패: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to stop recording: {str(e)}")

        @self.app.get("/api/recording/status")
        async def get_recording_status():
            """녹화 상태 조회"""
            status = {}

            for camera_id in [0, 1]:
                recorder = self.camera_manager.recorders.get(camera_id)
                camera_active = camera_id in self.camera_manager.camera_instances

                if recorder:
                    status[f"camera_{camera_id}"] = {
                        "recording": recorder.is_recording,
                        "camera_active": camera_active,
                        "status": "recording" if recorder.is_recording else "idle"
                    }
                else:
                    status[f"camera_{camera_id}"] = {
                        "recording": False,
                        "camera_active": camera_active,
                        "status": "not_initialized"
                    }

            return status

    # 기존 프로세스 기반 녹화 관련 함수들은 제거됨
    # 이제 프레임 공유 방식을 사용하여 스트리밍 중단 없이 녹화