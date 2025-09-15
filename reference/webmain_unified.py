#!/usr/bin/env python3
"""
통합 카메라 관리자를 사용한 CCTV 시스템
ISP 리소스 경합 문제 완전 해결 버전
"""

import asyncio
import signal
import sys
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import logging
from pathlib import Path

# 통합 카메라 관리자 임포트
from camera_manager import camera_manager, CameraMode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# FastAPI 앱 생성
app = FastAPI(title="통합 CCTV 시스템")

# 정적 파일 서빙
static_path = Path("web/static")
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 카메라 초기화"""
    logger.info("[STARTUP] 통합 CCTV 시스템 시작")

    # 두 카메라 모두 스트리밍 모드로 초기화
    camera_manager.initialize_camera(0, CameraMode.STREAMING)
    camera_manager.initialize_camera(1, CameraMode.STREAMING)

@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 정리"""
    logger.info("[SHUTDOWN] 시스템 종료 중...")
    camera_manager.cleanup_all()

@app.get("/")
async def root():
    """메인 페이지"""
    index_file = static_path / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse("<h1>통합 CCTV 시스템</h1>")

@app.get("/stream/{camera_id}")
async def stream_camera(camera_id: int):
    """개별 카메라 스트리밍"""
    if camera_id not in [0, 1]:
        raise HTTPException(status_code=404, detail="Invalid camera ID")

    # 스트리밍 모드 확인/전환
    current_mode = camera_manager.camera_modes.get(camera_id, CameraMode.IDLE)
    if current_mode == CameraMode.RECORDING:
        return HTTPException(status_code=423, detail="Camera is recording")

    if current_mode != CameraMode.STREAMING:
        camera_manager.switch_mode(camera_id, CameraMode.STREAMING)

    def generate():
        """MJPEG 스트림 생성"""
        while True:
            frame_data = camera_manager.capture_frame_for_streaming(camera_id)
            if frame_data:
                yield b'--frame\r\n'
                yield b'Content-Type: image/jpeg\r\n'
                yield f'Content-Length: {len(frame_data)}\r\n\r\n'.encode()
                yield frame_data
                yield b'\r\n'
            else:
                # 프레임 없으면 잠시 대기
                import time
                time.sleep(0.033)  # ~30fps

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/stream")
async def stream_dual():
    """듀얼 카메라 스트림 (카메라 0 기본)"""
    return await stream_camera(0)

@app.post("/api/switch/{camera_id}")
async def switch_camera(camera_id: int):
    """카메라 전환"""
    if camera_id not in [0, 1]:
        raise HTTPException(status_code=404, detail="Invalid camera ID")

    return {"success": True, "camera": camera_id}

@app.post("/api/start_recording/{camera_id}")
async def start_recording(camera_id: int):
    """녹화 시작 API - 간소화 버전"""
    if camera_id not in [0, 1]:
        raise HTTPException(status_code=404, detail="Invalid camera ID")

    try:
        # 녹화 파일 경로 생성
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"videos/cam{camera_id}/cam{camera_id}_{timestamp}.mp4"

        # 디렉토리 생성
        Path(f"videos/cam{camera_id}").mkdir(parents=True, exist_ok=True)

        # 간단한 녹화 - 외부 스크립트 호출
        import subprocess
        import asyncio

        # 백그라운드에서 30초 녹화 실행
        async def run_recording():
            try:
                process = await asyncio.create_subprocess_exec(
                    "python3", f"rec_cam{camera_id}.py",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                # 30초 후 프로세스 종료
                await asyncio.sleep(30)
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
                logger.info(f"[OK] 카메라 {camera_id} 30초 녹화 완료")
            except Exception as e:
                logger.error(f"[ERROR] 녹화 프로세스 오류: {e}")

        # 백그라운드 태스크 실행
        asyncio.create_task(run_recording())

        return {"success": True, "message": f"Recording started for camera {camera_id} (30 seconds)"}

    except Exception as e:
        logger.error(f"[ERROR] 녹화 시작 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

@app.post("/api/stop_recording/{camera_id}")
async def stop_recording(camera_id: int):
    """녹화 중지 API"""
    if camera_id not in [0, 1]:
        raise HTTPException(status_code=404, detail="Invalid camera ID")

    success = camera_manager.stop_recording(camera_id)

    if success:
        return {"success": True, "message": "Recording stopped"}
    else:
        raise HTTPException(status_code=400, detail="Camera not recording")

@app.get("/api/status")
async def get_status():
    """시스템 상태 API"""
    return camera_manager.get_status()

@app.get("/api/stats")
async def get_stats():
    """통계 정보 (기존 호환성)"""
    status = camera_manager.get_status()

    # 활성 스트리밍 카운트
    active_streams = sum(
        1 for cam_info in status["cameras"].values()
        if cam_info["mode"] == "streaming"
    )

    return {
        "active_clients": active_streams,
        "max_clients": 2,
        "resolution": status["resolution"],
        "cameras": status["cameras"]
    }

@app.post("/api/dual_mode/{enable}")
async def set_dual_mode(enable: bool):
    """듀얼 모드 설정 API (호환성)"""
    if enable:
        # 두 카메라 모두 스트리밍 모드로
        camera_manager.initialize_camera(0, CameraMode.STREAMING)
        camera_manager.initialize_camera(1, CameraMode.STREAMING)
    else:
        # 카메라 1만 정지
        camera_manager.cleanup_camera(1)

    return {"success": True, "dual_mode": enable}

@app.get("/api/recording/status")
async def get_recording_status():
    """녹화 상태 API"""
    status = camera_manager.get_status()

    recording_cameras = []
    for cam_id, cam_info in status["cameras"].items():
        if cam_info.get("recording", False):
            recording_cameras.append(cam_id)

    return {
        "is_recording": len(recording_cameras) > 0,
        "recording_cameras": recording_cameras,
        "cameras": status["cameras"]
    }

@app.head("/stream/{camera_id}")
async def stream_camera_head(camera_id: int):
    """스트림 HEAD 요청 (연결 테스트용)"""
    if camera_id not in [0, 1]:
        raise HTTPException(status_code=404, detail="Invalid camera ID")

    return Response(status_code=200)

@app.head("/stream")
async def stream_head():
    """메인 스트림 HEAD 요청"""
    return Response(status_code=200)

# 웹 인터페이스 호환을 위한 추가 API
@app.post("/api/recording/start/{camera_id}")
async def start_recording_alt(camera_id: int):
    """녹화 시작 API (웹 인터페이스 호환)"""
    return await start_recording(camera_id)

@app.post("/api/recording/stop/{camera_id}")
async def stop_recording_alt(camera_id: int):
    """녹화 중지 API (웹 인터페이스 호환)"""
    return await stop_recording(camera_id)

def main():
    """메인 함수"""
    logger.info("[INIT] 통합 CCTV 시스템 시작")

    # 개선된 시그널 핸들러
    def shutdown_handler(sig, frame):
        logger.info(f"\n[SIGNAL] 종료 신호 수신 (시그널: {sig})")
        try:
            camera_manager.cleanup_all()
            logger.info("[OK] 카메라 정리 완료")
        except Exception as e:
            logger.error(f"[ERROR] 정리 중 오류: {e}")
        finally:
            import os
            logger.info("[EXIT] 강제 종료")
            os._exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # 서버 실행
    try:
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8001,
            log_level="info"
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None

        asyncio.run(server.serve())
    except KeyboardInterrupt:
        logger.info("[INTERRUPT] KeyboardInterrupt 수신")
        shutdown_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"[ERROR] 서버 오류: {e}")
        shutdown_handler(signal.SIGTERM, None)

if __name__ == "__main__":
    main()