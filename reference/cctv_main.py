#!/usr/bin/env python3
"""
듀얼 카메라 토글 스트리밍 서버
"""

import subprocess
import signal
import asyncio
import time
import atexit
import sys
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
import uvicorn

# 로깅 시스템 import
from reference.logger import setup_logger, get_logger, cleanup_logger, log_execution_time

app = FastAPI()

# 로거 초기화
logger = setup_logger(
    log_dir="logs",
    log_level="INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    console_output=True,
    async_logging=True
)

# 전역 변수
current_camera = 0
current_resolution = "640x480"  # 기본 해상도
camera_processes = {}
stream_stats = {
    0: {"frame_count": 0, "avg_frame_size": 0, "fps": 0, "last_update": 0},
    1: {"frame_count": 0, "avg_frame_size": 0, "fps": 0, "last_update": 0}
}

# 단일 클라이언트 제한
active_clients = set()  # 활성 클라이언트 IP 집합
MAX_CLIENTS = 1  # 최대 1개 클라이언트

# 해상도 설정
RESOLUTIONS = {
    "640x480": {"width": 640, "height": 480, "name": "480p"},
    "1280x720": {"width": 1280, "height": 720, "name": "720p"}
}

@log_execution_time("카메라_스트림_시작")
def start_camera_stream(camera_id: int, resolution: str = None):
    """카메라 스트리밍 시작"""
    logger.info(f"[START] 카메라 {camera_id} 스트리밍 시작 요청 (해상도: {resolution or current_resolution})")
    
    if camera_id in camera_processes:
        logger.info(f"기존 카메라 {camera_id} 프로세스 종료 중...")
        stop_camera_stream(camera_id)
    
    # 해상도 설정
    if resolution is None:
        resolution = current_resolution
    
    res_config = RESOLUTIONS.get(resolution, RESOLUTIONS["640x480"])
    width = res_config["width"]
    height = res_config["height"]
    
    cmd = [
        "rpicam-vid",
        "--camera", str(camera_id),
        "--width", str(width), "--height", str(height),
        "--framerate", "30",
        "--timeout", "0",
        "--nopreview",
        "--codec", "mjpeg",
        "--quality", "80",
        "--flush", "1",
        "--hflip",  # 좌우 반전 (거울모드)
        "--output", "-"
    ]
    
    logger.debug(f"rpicam-vid 명령어: {' '.join(cmd)}")
    
    try:
        # stderr를 /dev/null로 리다이렉트하여 버퍼 오버플로우 방지
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.DEVNULL,  # stderr 버퍼 오버플로우 방지
            bufsize=0  # 버퍼링 비활성화
        )
        camera_processes[camera_id] = process
        logger.info(f"[OK] Camera {camera_id} started at {resolution} (PID: {process.pid})")
        print(f"[OK] Camera {camera_id} started at {resolution} (PID: {process.pid})")
        return True
    except Exception as e:
        logger.error(f"[ERROR] Failed to start camera {camera_id}: {e}")
        print(f"[ERROR] Failed to start camera {camera_id}: {e}")
        return False

@log_execution_time("카메라_스트림_중지")
def stop_camera_stream(camera_id: int):
    """카메라 스트리밍 중지 - 강화된 프로세스 정리"""
    if camera_id in camera_processes:
        logger.info(f"[STOP] 카메라 {camera_id} 스트림 중지 시작")
        try:
            process = camera_processes[camera_id]
            pid = process.pid
            
            # 1. 프로세스 상태 확인
            if process.poll() is None:  # 프로세스가 아직 실행 중
                logger.debug(f"카메라 {camera_id} 프로세스 (PID: {pid}) SIGTERM 신호 전송")
                
                # 2. 정상 종료 시도 (SIGTERM)
                try:
                    process.send_signal(signal.SIGTERM)
                    process.wait(timeout=3)
                    logger.debug(f"카메라 {camera_id} 프로세스 정상 종료")
                except subprocess.TimeoutExpired:
                    logger.warning(f"[WARN] SIGTERM timeout, 강제 종료 시도 (PID: {pid})")
                    
                    # 3. 강제 종료 시도 (SIGKILL)
                    try:
                        process.kill()
                        process.wait(timeout=3)
                        logger.debug(f"카메라 {camera_id} 프로세스 강제 종료 완료")
                    except subprocess.TimeoutExpired:
                        logger.error(f"[ERROR] SIGKILL timeout for PID {pid}")
                        
                        # 4. 시스템 레벨 강제 종료
                        try:
                            import os
                            os.kill(pid, signal.SIGKILL)
                            logger.warning(f"[KILL] 시스템 레벨 강제 종료 PID {pid}")
                        except ProcessLookupError:
                            logger.info(f"[OK] 프로세스 {pid} 이미 종료됨")
                        except Exception as kill_error:
                            logger.error(f"[ERROR] 프로세스 {pid} 강제 종료 실패: {kill_error}")
            
            # 5. stdout 버퍼 완전 정리
            if process.stdout:
                try:
                    # 남은 모든 데이터를 읽어서 버림 (블로킹 방지를 위한 비블로킹 읽기)
                    import select
                    import fcntl
                    import os
                    
                    fd = process.stdout.fileno()
                    # 논블로킹 모드 설정
                    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
                    
                    # 모든 남은 데이터 읽기
                    total_read = 0
                    while True:
                        if select.select([process.stdout], [], [], 0.1)[0]:
                            data = process.stdout.read(65536)  # 64KB 청크
                            if not data:
                                break
                            total_read += len(data)
                            if total_read > 10 * 1024 * 1024:  # 10MB 제한
                                logger.warning(f"[WARN] 버퍼 정리 중 10MB 제한 도달, 강제 종료")
                                break
                        else:
                            break
                    
                    if total_read > 0:
                        logger.debug(f"[BUFFER] {total_read} bytes 버퍼 정리됨")
                        
                except Exception as buffer_error:
                    logger.warning(f"[WARN] 버퍼 정리 중 오류 (무시): {buffer_error}")
                finally:
                    try:
                        process.stdout.close()
                    except:
                        pass
            
            # 6. 프로세스 최종 상태 확인
            final_status = process.poll()
            if final_status is not None:
                logger.info(f"[STOP] 프로세스 {pid} 종료 상태: {final_status}")
            else:
                logger.error(f"[ERROR] 프로세스 {pid}가 여전히 실행 중일 수 있음")
            
            # 7. 프로세스 딕셔너리에서 제거
            del camera_processes[camera_id]
            
            # 8. 통계 초기화
            stream_stats[camera_id] = {"frame_count": 0, "avg_frame_size": 0, "fps": 0, "last_update": 0}
            
            # 9. 추가 정리 대기 시간 (카메라 하드웨어 해제 대기)
            import time
            time.sleep(0.5)
            
            # 10. 가비지 컬렉션 강제 실행
            import gc
            gc.collect()
            
            logger.info(f"[STOP] Camera {camera_id} stopped and cleaned (PID: {pid})")
            print(f"[STOP] Camera {camera_id} stopped and cleaned (PID: {pid})")
            
        except Exception as e:
            logger.error(f"[ERROR] Error stopping camera {camera_id}: {e}")
            print(f"[ERROR] Error stopping camera {camera_id}: {e}")
            # 비상 정리 - 딕셔너리에서라도 제거
            if camera_id in camera_processes:
                del camera_processes[camera_id]
    else:
        logger.warning(f"카메라 {camera_id} 프로세스가 존재하지 않음")

def generate_mjpeg_stream(camera_id: int, client_ip: str = None):
    """최적화된 MJPEG 스트림 생성 - 메모리 효율 개선"""
    if camera_id not in camera_processes:
        return
    
    process = camera_processes[camera_id]
    
    # 현재 해상도에 따른 동적 설정
    is_720p = current_resolution == "1280x720"
    
    # 해상도별 최적화 파라미터 (버퍼 크기 감소)
    if is_720p:
        chunk_size = 32768  # 32KB 청크
        buffer_limit = 1024 * 1024  # 1MB 버퍼 (2MB → 1MB 감소)
        buffer_keep = 512 * 1024  # 512KB 유지
        frame_min_size = 5000  # 5KB
        frame_max_size = 500000  # 500KB
        cleanup_threshold = 100000  # 100KB
        cleanup_keep = 20000  # 20KB
    else:
        chunk_size = 16384  # 16KB 청크
        buffer_limit = 256 * 1024  # 256KB 버퍼 (512KB → 256KB 감소)
        buffer_keep = 128 * 1024  # 128KB 유지
        frame_min_size = 2000  # 2KB
        frame_max_size = 200000  # 200KB
        cleanup_threshold = 50000  # 50KB
        cleanup_keep = 10000  # 10KB
    
    # collections.deque 사용으로 메모리 효율 개선
    from collections import deque
    buffer = bytearray()
    frame_count = 0
    total_frame_size = 0
    start_time = time.time()
    last_fps_update = start_time
    last_gc_time = start_time  # 가비지 컬렉션 타이머
    
    logger.info(f"[STREAM] Starting {current_resolution} stream for camera {camera_id}")
    logger.debug(f"[CONFIG] Buffer config: {buffer_limit//1024}KB limit, {chunk_size//1024}KB chunks")
    print(f"[STREAM] Starting {current_resolution} stream for camera {camera_id}")
    print(f"[CONFIG] Buffer config: {buffer_limit//1024}KB limit, {chunk_size//1024}KB chunks")
    
    # 클라이언트 등록
    if client_ip:
        active_clients.add(client_ip)
        logger.info(f"[CLIENT] Client connected: {client_ip} (Total: {len(active_clients)})")
        print(f"[CLIENT] Client connected: {client_ip} (Total: {len(active_clients)})")
    
    try:
        while True:
            try:
                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    print(f"[WARN] No data from camera {camera_id}, stream ending")
                    break
            except Exception as e:
                print(f"[ERROR] Read error from camera {camera_id}: {e}")
                break
                
            buffer.extend(chunk)
            
            # 동적 버퍼 크기 제한 - 인플레이스 삭제로 메모리 최적화
            if len(buffer) > buffer_limit:
                excess = len(buffer) - buffer_keep
                del buffer[:excess]  # 인플레이스 삭제로 새 객체 생성 방지
            
            # JPEG 프레임 찾기
            while True:
                start_idx = buffer.find(b'\xff\xd8')
                if start_idx == -1:
                    if len(buffer) > cleanup_threshold:
                        excess = len(buffer) - cleanup_keep
                        del buffer[:excess]  # 인플레이스 삭제로 메모리 최적화
                    break
                    
                end_idx = buffer.find(b'\xff\xd9', start_idx + 2)
                if end_idx == -1:
                    if start_idx > 0:
                        buffer = buffer[start_idx:]
                    break
                
                # 완전한 프레임 추출
                frame = buffer[start_idx:end_idx + 2]
                buffer = buffer[end_idx + 2:]
                
                # 해상도별 프레임 크기 검증
                frame_size = len(frame)
                if frame_min_size < frame_size < frame_max_size:
                    try:
                        yield b'--frame\r\n'
                        yield b'Content-Type: image/jpeg\r\n'
                        yield f'Content-Length: {frame_size}\r\n\r\n'.encode()
                        yield bytes(frame)
                        yield b'\r\n'
                        
                        frame_count += 1
                        total_frame_size += frame_size
                        
                        # 프레임 카운터 자동 리셋 (10만 프레임마다 = 약 55분)
                        if frame_count >= 100000:
                            print(f"[RESET] Auto-reset: Frame counter reached 100K, resetting for memory stability")
                            frame_count = 1  # 나누기 오류 방지를 위해 1로 설정
                            total_frame_size = frame_size
                            start_time = time.time()
                            last_fps_update = start_time
                            last_gc_time = start_time
                            # 통계 초기화
                            stream_stats[camera_id] = {"frame_count": 1, "avg_frame_size": frame_size, "fps": 30.0, "last_update": start_time}
                        
                        # FPS 및 통계 업데이트 (매초마다)
                        current_time = time.time()
                        if current_time - last_fps_update >= 1.0:
                            elapsed = current_time - start_time
                            fps = frame_count / elapsed if elapsed > 0 else 0
                            avg_size = total_frame_size // frame_count if frame_count > 0 else 0
                            
                            stream_stats[camera_id].update({
                                "frame_count": frame_count,
                                "avg_frame_size": avg_size,
                                "fps": round(fps, 1),
                                "last_update": current_time
                            })
                            last_fps_update = current_time
                        
                        # 주기적 가비지 컬렉션 (30초마다)
                        if current_time - last_gc_time > 30:
                            import gc
                            gc.collect()
                            last_gc_time = current_time
                        
                        if frame_count % 150 == 0:  # 150프레임마다 로그
                            print(f"[STATS] Camera {camera_id} ({current_resolution}): {frame_count} frames, {stream_stats[camera_id]['fps']} fps, avg {frame_size//1024}KB")
                    
                    except Exception as e:
                        print(f"[ERROR] Frame yield error for camera {camera_id}: {e}")
                        break
                else:
                    if frame_count % 100 == 0 and frame_size > 0:  # 가끔 로그
                        print(f"[WARN] Frame size {frame_size//1024}KB out of range ({frame_min_size//1024}-{frame_max_size//1024}KB)")
                        
    except Exception as e:
        print(f"[ERROR] Stream error for camera {camera_id}: {e}")
    finally:
        # 클라이언트 연결 종료
        if client_ip and client_ip in active_clients:
            active_clients.remove(client_ip)
            print(f"[CLIENT] Client disconnected: {client_ip} (Remaining: {len(active_clients)})")
        print(f"[END] Camera {camera_id} ({current_resolution}) stream ended (total: {frame_count} frames)")
        # 스트림 종료 시 통계 초기화
        if camera_id in stream_stats:
            stream_stats[camera_id]["last_update"] = 0

@app.get("/")
async def root():
    """메인 페이지"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>듀얼 카메라 토글</title>
        <meta charset="UTF-8">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 0; padding: 0;
                background: #f5f5f5;
                text-align: center;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
            }
            .container {
                flex: 1;
                display: flex;
                flex-direction: column;
                background: white;
                padding: 15px;
                height: 100vh;
                box-sizing: border-box;
            }
            h1 { color: #333; margin-bottom: 20px; }
            .video-container {
                flex: 1;
                display: flex;
                justify-content: center;
                align-items: center;
                border: 2px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                margin: 10px 0;
                min-height: 60vh;
            }
            .video-container.resolution-640 {
                max-height: 55vh;
                max-width: 70%;
                margin: 10px auto;
            }
            .video-container.resolution-720 {
                max-height: 75vh;
                max-width: 95%;
                margin: 10px auto;
            }
            img { 
                width: 100%; 
                height: 100%;
                object-fit: contain;
                display: block;
            }
            .controls {
                margin: 10px 0;
                display: flex;
                gap: 20px;
                justify-content: center;
                flex-wrap: wrap;
                flex-shrink: 0;
            }
            .control-section {
                text-align: center;
            }
            .control-section h3 {
                margin: 0 0 10px 0;
                color: #495057;
                font-size: 16px;
            }
            button {
                font-size: 14px;
                padding: 10px 20px;
                margin: 0 5px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                transition: all 0.3s;
                display: inline-block;
            }
            .camera-btn, .resolution-btn {
                background: #f8f9fa;
                color: #495057;
                border: 1px solid #dee2e6;
            }
            .camera-btn:hover, .resolution-btn:hover {
                background: #e9ecef;
            }
            .camera-btn.active, .resolution-btn.active {
                background: #28a745;
                color: white;
                border: 1px solid #28a745;
            }
            .exit-btn {
                background: #dc3545;
                color: white;
                border: 1px solid #dc3545;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                margin: 0 5px;
                border-radius: 5px;
                cursor: pointer;
                transition: all 0.3s;
                display: inline-block;
                text-decoration: none;
            }
            .exit-btn:hover {
                background: #c82333;
                border: 1px solid #c82333;
                color: white;
                text-decoration: none;
            }
            .video-container {
                margin: 20px 0;
                border: 2px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                background: #f8f9fa;
            }
            .video-container img { 
                width: 100%; 
                height: auto;
                display: block;
            }
            .status {
                margin: 10px 0;
                padding: 10px;
                background: #e9ecef;
                border-radius: 8px;
                font-size: 12px;
                flex-shrink: 0;
            }
            .status-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
            }
            .status-item {
                padding: 8px;
                background: white;
                border-radius: 4px;
                border-left: 3px solid #007bff;
            }
            .status-item strong {
                color: #495057;
            }
            .status-item span {
                color: #007bff;
                font-weight: bold;
            }
            
            /* 하트비트 인디케이터 스타일 */
            .heartbeat-container {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                margin-left: 20px;
                vertical-align: middle;
            }
            
            .heartbeat-indicator {
                width: 20px;
                height: 20px;
                border-radius: 50%;
                margin-right: 8px;
                position: relative;
            }
            
            .heartbeat-indicator.green {
                background: #28a745;
                animation: pulse-green 1s infinite;
                box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.7);
            }
            
            .heartbeat-indicator.yellow {
                background: #ffc107;
                animation: pulse-yellow 2s infinite;
                box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.7);
            }
            
            .heartbeat-indicator.red {
                background: #dc3545;
                animation: none;
            }
            
            .heartbeat-indicator.black {
                background: #6c757d;
                animation: none;
            }
            
            @keyframes pulse-green {
                0% {
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.7);
                }
                70% {
                    transform: scale(1);
                    box-shadow: 0 0 0 10px rgba(40, 167, 69, 0);
                }
                100% {
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0);
                }
            }
            
            @keyframes pulse-yellow {
                0% {
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.7);
                }
                70% {
                    transform: scale(1);
                    box-shadow: 0 0 0 10px rgba(255, 193, 7, 0);
                }
                100% {
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 rgba(255, 193, 7, 0);
                }
            }
            
            .heartbeat-text {
                font-size: 12px;
                color: #495057;
                font-weight: bold;
            }
            
            /* 네트워크 품질 바 스타일 */
            .network-quality {
                margin-top: 10px;
                padding: 8px;
                background: #f8f9fa;
                border-radius: 4px;
                border-left: 3px solid #17a2b8;
                font-size: 11px;
                text-align: center;
            }
            
            .quality-bar {
                font-family: monospace;
                font-size: 14px;
                font-weight: bold;
                margin: 5px 0;
                letter-spacing: 1px;
            }
            
            .quality-bar.excellent { color: #28a745; }
            .quality-bar.good { color: #ffc107; }
            .quality-bar.poor { color: #fd7e14; }
            .quality-bar.critical { color: #dc3545; }
            .quality-bar.down { color: #6c757d; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>듀얼 카메라 토글 스트리밍</h1>
            
            <div class="status">
                <div class="status-grid">
                    <div class="status-item">
                        <strong>활성 카메라:</strong> <span id="current-camera">0</span>
                    </div>
                    <div class="status-item">
                        <strong>해상도:</strong> <span id="resolution">640×480</span>
                    </div>
                    <div class="status-item">
                        <strong>코덱:</strong> <span id="codec">MJPEG</span>
                    </div>
                    <div class="status-item">
                        <strong>품질:</strong> <span id="quality">80%</span>
                    </div>
                    <div class="status-item">
                        <strong>FPS:</strong> <span id="fps">0.0</span>
                    </div>
                    <div class="status-item">
                        <strong>프레임 수:</strong> <span id="frame-count">0</span>
                    </div>
                    <div class="status-item">
                        <strong>평균 프레임 크기:</strong> <span id="frame-size">0 KB</span>
                    </div>
                    <div class="status-item">
                        <strong>상태:</strong> <span id="stream-status">준비 중</span>
                    </div>
                </div>
            </div>
            
            <div class="controls">
                <div class="control-section">
                    <h3>카메라 선택</h3>
                    <button class="camera-btn active" id="cam0-btn" onclick="switchCamera(0)">
                        카메라 0
                    </button>
                    <button class="camera-btn" id="cam1-btn" onclick="switchCamera(1)">
                        카메라 1
                    </button>
                </div>
                
                <div class="control-section">
                    <h3>해상도 선택</h3>
                    <button class="resolution-btn active" id="res-640-btn" onclick="changeResolution('640x480')">
                        📺 480p (640×480)
                    </button>
                    <button class="resolution-btn" id="res-720-btn" onclick="changeResolution('1280x720')">
                        📺 720p (1280×720)
                    </button>
                </div>
                
                <div class="control-section">
                    <h3>시스템 제어</h3>
                    <div style="display: flex; align-items: center; justify-content: center;">
                        <a href="/exit" class="exit-btn">
                            🛑  CCTV 종료
                        </a>
                        <!-- 하트비트 인디케이터 -->
                        <div class="heartbeat-container">
                            <div class="heartbeat-indicator green" id="heartbeat-indicator"></div>
                            <span class="heartbeat-text" id="heartbeat-text">LIVE</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="video-container resolution-640" id="video-container">
                <img id="video-stream" src="/stream" alt="Live Stream">
            </div>
            
            <!-- 네트워크 품질 바 -->
            <div class="network-quality">
                <div><strong>Network Quality:</strong> <span id="quality-status">Excellent</span></div>
                <div class="quality-bar excellent" id="quality-bar">[██████████] 100%</div>
            </div>
            
            <p>메모리 누수 방지 및 실시간 모니터링이 개선된 버전입니다</p>
        </div>
        
        <script>
            let currentCamera = 0;
            let lastFrameTime = Date.now();
            let streamQuality = 100;
            
            // 스트림 모니터링 시스템
            function initStreamMonitoring() {
                const videoStream = document.getElementById('video-stream');
                
                // 프레임 로드 감지
                videoStream.addEventListener('load', function() {
                    lastFrameTime = Date.now();
                    updateStreamQuality(true);
                });
                
                // 에러 감지
                videoStream.addEventListener('error', function() {
                    updateStreamQuality(false);
                });
                
                // 0.5초마다 하트비트 상태 체크
                setInterval(checkHeartbeat, 500);
                
                // 2초마다 네트워크 품질 업데이트
                setInterval(updateNetworkQuality, 2000);
            }
            
            function checkHeartbeat() {
                const now = Date.now();
                const elapsed = (now - lastFrameTime) / 1000;
                const indicator = document.getElementById('heartbeat-indicator');
                const text = document.getElementById('heartbeat-text');
                
                // 하트비트 상태 업데이트
                indicator.className = 'heartbeat-indicator';
                
                if (elapsed < 1) {
                    indicator.classList.add('green');
                    text.textContent = 'LIVE';
                } else if (elapsed < 3) {
                    indicator.classList.add('yellow');
                    text.textContent = 'DELAY';
                } else if (elapsed < 5) {
                    indicator.classList.add('red');
                    text.textContent = 'ERROR';
                } else {
                    indicator.classList.add('black');
                    text.textContent = 'OFFLINE';
                }
            }
            
            function updateStreamQuality(frameReceived) {
                const now = Date.now();
                const elapsed = (now - lastFrameTime) / 1000;
                
                if (frameReceived) {
                    streamQuality = Math.min(100, streamQuality + 5);
                } else if (elapsed > 3) {
                    streamQuality = Math.max(0, streamQuality - 20);
                } else if (elapsed > 1) {
                    streamQuality = Math.max(30, streamQuality - 5);
                }
            }
            
            function updateNetworkQuality() {
                const qualityBar = document.getElementById('quality-bar');
                const qualityStatus = document.getElementById('quality-status');
                
                // 품질 바 생성
                const filled = Math.floor(streamQuality / 10);
                const empty = 10 - filled;
                const bar = '[' + '█'.repeat(filled) + '░'.repeat(empty) + '] ' + streamQuality + '%';
                
                qualityBar.textContent = bar;
                qualityBar.className = 'quality-bar';
                
                // 품질 레벨 설정
                if (streamQuality >= 80) {
                    qualityBar.classList.add('excellent');
                    qualityStatus.textContent = 'Excellent';
                } else if (streamQuality >= 60) {
                    qualityBar.classList.add('good');
                    qualityStatus.textContent = 'Good';
                } else if (streamQuality >= 40) {
                    qualityBar.classList.add('poor');
                    qualityStatus.textContent = 'Poor';
                } else if (streamQuality >= 20) {
                    qualityBar.classList.add('critical');
                    qualityStatus.textContent = 'Critical';
                } else {
                    qualityBar.classList.add('down');
                    qualityStatus.textContent = 'System Down';
                }
            }
            
            function switchCamera(cameraId) {
                fetch(`/switch/${cameraId}`, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            currentCamera = cameraId;
                            updateUI();
                            // 스트림 새로고침
                            const img = document.getElementById('video-stream');
                            img.src = `/stream?t=${Date.now()}`;
                            lastFrameTime = Date.now(); // 프레임 시간 리셋
                        }
                    })
                    .catch(error => console.error('Error:', error));
            }
            
            function updateUI() {
                // 버튼 상태 업데이트
                document.getElementById('cam0-btn').classList.toggle('active', currentCamera === 0);
                document.getElementById('cam1-btn').classList.toggle('active', currentCamera === 1);
                
                // 현재 카메라 표시
                document.getElementById('current-camera').textContent = currentCamera;
            }
            
            function changeResolution(resolution) {
                fetch(`/api/resolution/${resolution}`, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            // 해상도 버튼 상태 업데이트
                            document.getElementById('res-640-btn').classList.toggle('active', resolution === '640x480');
                            document.getElementById('res-720-btn').classList.toggle('active', resolution === '1280x720');
                            
                            // 비디오 컨테이너 클래스 업데이트
                            const videoContainer = document.getElementById('video-container');
                            videoContainer.className = 'video-container ' + (resolution === '640x480' ? 'resolution-640' : 'resolution-720');
                            
                            // 스트림 새로고침
                            const img = document.getElementById('video-stream');
                            img.src = `/stream?t=${Date.now()}`;
                            
                            console.log(`Resolution changed to ${resolution}`);
                        }
                    })
                    .catch(error => {
                        console.error('Resolution change error:', error);
                        alert(`해상도 변경 실패: ${error.message}`);
                    });
            }
            
            function updateStats() {
                fetch('/api/stats')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('current-camera').textContent = data.current_camera;
                        document.getElementById('resolution').textContent = data.resolution;
                        document.getElementById('codec').textContent = data.codec;
                        document.getElementById('quality').textContent = data.quality;
                        
                        // 해상도 버튼 상태 업데이트
                        document.getElementById('res-640-btn').classList.toggle('active', data.resolution === '640x480');
                        document.getElementById('res-720-btn').classList.toggle('active', data.resolution === '1280x720');
                        
                        // 비디오 컨테이너 클래스도 업데이트
                        const videoContainer = document.getElementById('video-container');
                        if (videoContainer) {
                            videoContainer.className = 'video-container ' + (data.resolution === '640x480' ? 'resolution-640' : 'resolution-720');
                        }
                        
                        const stats = data.stats;
                        if (stats && Object.keys(stats).length > 0) {
                            document.getElementById('fps').textContent = stats.fps || '0.0';
                            document.getElementById('frame-count').textContent = stats.frame_count || '0';
                            document.getElementById('frame-size').textContent = 
                                stats.avg_frame_size ? Math.round(stats.avg_frame_size / 1024) + ' KB' : '0 KB';
                            
                            // 상태 표시
                            const now = Date.now() / 1000;
                            const lastUpdate = stats.last_update || 0;
                            const isActive = (now - lastUpdate) < 3; // 3초 이내 업데이트면 활성
                            
                            document.getElementById('stream-status').textContent = 
                                isActive ? '스트리밍 중' : '연결 끊김';
                            document.getElementById('stream-status').style.color = 
                                isActive ? '#28a745' : '#dc3545';
                        } else {
                            // 통계가 없으면 기본값
                            document.getElementById('fps').textContent = '0.0';
                            document.getElementById('frame-count').textContent = '0';
                            document.getElementById('frame-size').textContent = '0 KB';
                            document.getElementById('stream-status').textContent = '대기 중';
                            document.getElementById('stream-status').style.color = '#6c757d';
                        }
                    })
                    .catch(error => {
                        console.error('Stats update error:', error);
                        document.getElementById('stream-status').textContent = '오류';
                        document.getElementById('stream-status').style.color = '#dc3545';
                    });
            }
            
            // 스트림 오류 시 재시도 (하트비트 업데이트 추가)
            document.getElementById('video-stream').onerror = function() {
                updateStreamQuality(false);
                setTimeout(() => {
                    this.src = `/stream?t=${Date.now()}`;
                }, 2000);
            };
            
            // 페이지 로드 시 모니터링 시스템 시작
            document.addEventListener('DOMContentLoaded', function() {
                initStreamMonitoring(); // 스트림 모니터링 시작
                updateStats(); // 즉시 한 번 실행
                setInterval(updateStats, 1000); // 1초마다 업데이트
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/switch/{camera_id}")
async def switch_camera(camera_id: int):
    """카메라 전환"""
    global current_camera
    
    if camera_id not in [0, 1]:
        raise HTTPException(status_code=400, detail="Invalid camera ID")
    
    if camera_id == current_camera:
        return {"success": True, "message": f"Camera {camera_id} already active"}
    
    print(f"[SWITCH] Switching from camera {current_camera} to camera {camera_id}")
    
    # 기존 카메라 정지
    stop_camera_stream(current_camera)
    await asyncio.sleep(0.5)  # 잠시 대기
    
    # 새 카메라 시작
    success = start_camera_stream(camera_id)
    
    if success:
        current_camera = camera_id
        print(f"[OK] Successfully switched to camera {camera_id}")
        return {"success": True, "message": f"Switched to camera {camera_id}"}
    else:
        # 실패 시 기존 카메라 다시 시작
        start_camera_stream(current_camera)
        raise HTTPException(status_code=500, detail="Failed to switch camera")

@app.get("/stream")
async def video_stream(request: Request):
    """비디오 스트림 - 단일 클라이언트 제한"""
    client_ip = request.client.host
    
    # 단일 클라이언트 제한 확인
    if len(active_clients) >= MAX_CLIENTS and client_ip not in active_clients:
        print(f"[REJECT] Stream request rejected: {client_ip} (Max clients: {MAX_CLIENTS})")
        raise HTTPException(
            status_code=423,  # Locked
            detail=f"Maximum {MAX_CLIENTS} client(s) allowed. Another client is currently streaming."
        )
    
    print(f"[REQUEST] Stream request for camera {current_camera}")
    
    # 현재 카메라가 시작되지 않았으면 시작
    if current_camera not in camera_processes:
        success = start_camera_stream(current_camera)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start camera")
    
    return StreamingResponse(
        generate_mjpeg_stream(current_camera, client_ip),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/stats")
async def get_stream_stats():
    """스트리밍 통계 조회"""
    return {
        "current_camera": current_camera,
        "resolution": current_resolution,
        "codec": "MJPEG",
        "quality": "80%",
        "stats": stream_stats[current_camera] if current_camera in stream_stats else {}
    }

@app.post("/api/reset-stats")
async def reset_stream_stats():
    """수동 통계 리셋 API - 스트림 중단 없이 통계만 초기화"""
    global stream_stats
    
    # 현재 활성 카메라의 통계만 리셋
    if current_camera in stream_stats:
        stream_stats[current_camera] = {
            "frame_count": 0, 
            "avg_frame_size": 0, 
            "fps": 0.0, 
            "last_update": time.time()
        }
        print(f"[STATS] Manual stats reset for camera {current_camera}")
        
        # 강제 가비지 컬렉션
        import gc
        gc.collect()
        
        return {
            "success": True, 
            "message": f"Statistics reset for camera {current_camera}",
            "reset_time": time.time()
        }
    else:
        return {
            "success": False, 
            "message": "No active camera to reset",
            "current_camera": current_camera
        }

@app.post("/api/resolution/{resolution}")
async def change_resolution(resolution: str):
    """해상도 변경"""
    global current_resolution
    
    if resolution not in RESOLUTIONS:
        raise HTTPException(status_code=400, detail="Invalid resolution")
    
    print(f"[RESOLUTION] Changing resolution to {resolution}")
    
    # 현재 해상도와 같으면 변경하지 않음
    if resolution == current_resolution:
        return {"success": True, "message": f"Resolution already set to {resolution}"}
    
    old_resolution = current_resolution
    current_resolution = resolution
    
    # 현재 스트리밍 중인 카메라가 있으면 재시작
    if current_camera in camera_processes:
        print(f"[RESOLUTION] Stopping current camera {current_camera} for resolution change...")
        stop_camera_stream(current_camera)
        
        # 충분한 대기 시간으로 완전한 정리 보장
        await asyncio.sleep(2.0)  # 2초 대기
        
        print(f"[START] Starting camera {current_camera} with {resolution}...")
        success = start_camera_stream(current_camera, resolution)
        
        if success:
            # 카메라 시작 후 추가 안정화 대기
            await asyncio.sleep(1.0)
            print(f"[OK] Successfully changed resolution to {resolution}")
            return {"success": True, "message": f"Resolution changed to {resolution}"}
        else:
            # 실패 시 이전 해상도로 복원
            print(f"[ERROR] Failed to start with {resolution}, reverting to {old_resolution}")
            current_resolution = old_resolution
            await asyncio.sleep(1.0)
            start_camera_stream(current_camera, old_resolution)
            raise HTTPException(status_code=500, detail="Failed to change resolution")
    else:
        print(f"[OK] Resolution set to {resolution} (will apply when camera starts)")
        return {"success": True, "message": f"Resolution set to {resolution}"}

@app.post("/api/shutdown")
async def shutdown_system():
    """시스템 안전 종료"""
    print("[SHUTDOWN] System shutdown requested via web interface")
    
    # 모든 카메라 프로세스 정리
    for camera_id in list(camera_processes.keys()):
        print(f"[SHUTDOWN] Stopping camera {camera_id}...")
        stop_camera_stream(camera_id)
    
    print("[SHUTDOWN] All cameras stopped. Server will shutdown...")
    
    # 비동기적으로 서버 종료 (응답 후에 종료)
    import threading
    def delayed_shutdown():
        import time
        time.sleep(1)  # 응답 전송 대기
        import os
        os._exit(0)  # 강제 종료
    
    threading.Thread(target=delayed_shutdown, daemon=True).start()
    
    return {"success": True, "message": "System shutting down..."}

@app.get("/exit")
async def exit_system():
    """브라우저에서 /exit 접속 시 시스템 종료"""
    print("[EXIT] Exit requested via /exit URL")
    
    # 종료 페이지 HTML 반환
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>CCTV 종료</title>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .container {
                text-align: center;
                background: white;
                padding: 50px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
            }
            .emoji {
                font-size: 60px;
                margin: 20px 0;
            }
            .message {
                color: #666;
                font-size: 18px;
                line-height: 1.6;
            }
            .success {
                color: #28a745;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="emoji">🛑</div>
            <h1>CCTV 서비스 종료 중...</h1>
            <p class="message">
                <span class="success">✅ CCTV 서비스가 안전하게 종료되었습니다.</span><br><br>
                이제 모션 감지 시스템을 실행할 수 있습니다.<br>
                브라우저를 닫으셔도 됩니다.
            </p>
        </div>
        <script>
            // 3초 후 서버 종료
            setTimeout(() => {
                fetch('/api/shutdown', { method: 'POST' })
                    .catch(() => {
                        // 서버가 종료되면 에러가 발생하는 것이 정상
                    });
            }, 1000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기화"""
    logger.info("[START] CCTV 서버 시작 완료 - 첫 스트림 요청 시 카메라 활성화")
    print("[START] Server startup complete - camera will start on first stream request")

@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 모든 카메라 정리"""
    logger.info("[SHUTDOWN] CCTV 서버 종료 중 - 카메라 정리 시작")
    print("[SHUTDOWN] Cleaning up cameras...")
    for camera_id in list(camera_processes.keys()):
        stop_camera_stream(camera_id)
    cleanup_logger()

def cleanup_all_processes():
    """모든 카메라 프로세스 정리"""
    logger.info("[CLEANUP] 긴급 정리: 모든 카메라 프로세스 중지")
    print("[CLEANUP] Cleanup: Stopping all camera processes...")
    for camera_id in list(camera_processes.keys()):
        stop_camera_stream(camera_id)
    logger.info("[CLEANUP] All camera processes cleaned up")
    print("[CLEANUP] All camera processes cleaned up")
    cleanup_logger()

def signal_handler(signum, frame):
    """신호 핸들러 - SIGINT/SIGTERM 처리"""
    logger.warning(f"[SIGNAL] 시스템 종료 신호 수신: {signum} (Ctrl+C)")
    print(f"\n[SIGNAL] Received signal {signum} (Ctrl+C), cleaning up...")
    cleanup_all_processes()
    logger.info("[EXIT] CCTV 서버 완전 종료")
    print("[EXIT] Server shutdown complete")
    sys.exit(0)

if __name__ == "__main__":
    # 신호 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 종료 신호
    
    # atexit 핸들러 등록 (추가 안전장치)
    atexit.register(cleanup_all_processes)
    
    print("[INIT] Starting simple toggle camera server on port 8001")
    print("[INIT] Access web interface at: http://<your-pi-ip>:8001")
    print("[INIT] Signal handlers registered for clean shutdown")
    
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8001,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Keyboard interrupt received")
        cleanup_all_processes()
    except Exception as e:
        print(f"[ERROR] Server error: {e}")
        cleanup_all_processes()
    finally:
        print("[EXIT] Server shutdown complete")
