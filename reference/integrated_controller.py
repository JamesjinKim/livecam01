#!/usr/bin/env python3
"""
통합 제어 시스템
기존 토글 스트리밍 (main.py) + 모션 블랙박스 (detection_cam0,1.py) 관리
"""

import subprocess
import time
import signal
import threading
import psutil
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

app = FastAPI()

# 전역 변수
toggle_streaming_process = None  # 기존 picam2_main.py (포트 8001)
detection_cam0_process = None    # detection_cam0.py
detection_cam1_process = None    # detection_cam1.py

# 프로세스 관리
def start_toggle_streaming():
    """기존 토글 스트리밍 시작 (picam2_main.py)"""
    global toggle_streaming_process
    
    if toggle_streaming_process and toggle_streaming_process.poll() is None:
        print("📹 토글 스트리밍 이미 실행 중")
        return True
    
    try:
        # picam2_main.py 실행 (포트 8001)
        cmd = ["python3", "/home/shinho/shinho/livecam/picam2_main.py"]
        toggle_streaming_process = subprocess.Popen(cmd, 
                                                   stdout=subprocess.PIPE, 
                                                   stderr=subprocess.PIPE)
        print(f"📹 토글 스트리밍 시작 (PID: {toggle_streaming_process.pid}, 포트: 8001)")
        return True
    except Exception as e:
        print(f"❌ 토글 스트리밍 시작 실패: {e}")
        return False

def stop_toggle_streaming():
    """기존 토글 스트리밍 종료"""
    global toggle_streaming_process
    
    if toggle_streaming_process and toggle_streaming_process.poll() is None:
        try:
            # 정상 종료 시도
            toggle_streaming_process.send_signal(signal.SIGINT)
            
            try:
                toggle_streaming_process.wait(timeout=5)
                print("🛑 토글 스트리밍 정상 종료")
            except subprocess.TimeoutExpired:
                # 강제 종료
                toggle_streaming_process.kill()
                toggle_streaming_process.wait(timeout=2)
                print("⚠️ 토글 스트리밍 강제 종료")
            
            toggle_streaming_process = None
            return True
        except Exception as e:
            print(f"❌ 토글 스트리밍 종료 실패: {e}")
            return False
    return True

def start_detection_systems():
    """개별 모션 감지 시스템 시작 (detection_cam0.py, detection_cam1.py)"""
    global detection_cam0_process, detection_cam1_process
    
    success_count = 0
    
    # detection_cam0.py 시작
    if not detection_cam0_process or detection_cam0_process.poll() is not None:
        try:
            cmd = ["python3", "/home/shinho/shinho/livecam/detection_cam0.py"]
            detection_cam0_process = subprocess.Popen(cmd, 
                                                     stdout=subprocess.PIPE, 
                                                     stderr=subprocess.PIPE)
            print(f"📹 Detection Cam0 시작 (PID: {detection_cam0_process.pid})")
            success_count += 1
        except Exception as e:
            print(f"❌ Detection Cam0 시작 실패: {e}")
    else:
        print("📹 Detection Cam0 이미 실행 중")
        success_count += 1
    
    # detection_cam1.py 시작
    if not detection_cam1_process or detection_cam1_process.poll() is not None:
        try:
            cmd = ["python3", "/home/shinho/shinho/livecam/detection_cam1.py"]
            detection_cam1_process = subprocess.Popen(cmd, 
                                                     stdout=subprocess.PIPE, 
                                                     stderr=subprocess.PIPE)
            print(f"📹 Detection Cam1 시작 (PID: {detection_cam1_process.pid})")
            success_count += 1
        except Exception as e:
            print(f"❌ Detection Cam1 시작 실패: {e}")
    else:
        print("📹 Detection Cam1 이미 실행 중")
        success_count += 1
    
    return success_count == 2

def stop_detection_systems():
    """개별 모션 감지 시스템 종료"""
    global detection_cam0_process, detection_cam1_process
    
    success_count = 0
    
    # detection_cam0.py 종료
    if detection_cam0_process and detection_cam0_process.poll() is None:
        try:
            detection_cam0_process.send_signal(signal.SIGINT)
            try:
                detection_cam0_process.wait(timeout=5)
                print("🛑 Detection Cam0 정상 종료")
            except subprocess.TimeoutExpired:
                detection_cam0_process.kill()
                detection_cam0_process.wait(timeout=2)
                print("⚠️ Detection Cam0 강제 종료")
            detection_cam0_process = None
            success_count += 1
        except Exception as e:
            print(f"❌ Detection Cam0 종료 실패: {e}")
    else:
        success_count += 1
    
    # detection_cam1.py 종료
    if detection_cam1_process and detection_cam1_process.poll() is None:
        try:
            detection_cam1_process.send_signal(signal.SIGINT)
            try:
                detection_cam1_process.wait(timeout=5)
                print("🛑 Detection Cam1 정상 종료")
            except subprocess.TimeoutExpired:
                detection_cam1_process.kill()
                detection_cam1_process.wait(timeout=2)
                print("⚠️ Detection Cam1 강제 종료")
            detection_cam1_process = None
            success_count += 1
        except Exception as e:
            print(f"❌ Detection Cam1 종료 실패: {e}")
    else:
        success_count += 1
    
    return success_count == 2

def get_system_status():
    """통합 시스템 상태 조회"""
    toggle_running = toggle_streaming_process and toggle_streaming_process.poll() is None
    detection_cam0_running = detection_cam0_process and detection_cam0_process.poll() is None
    detection_cam1_running = detection_cam1_process and detection_cam1_process.poll() is None
    
    return {
        "toggle_streaming": {
            "running": toggle_running,
            "pid": toggle_streaming_process.pid if toggle_running else None,
            "port": 8001,
            "description": "카메라 0↔1 토글 스트리밍"
        },
        "detection_systems": {
            "cam0": {
                "running": detection_cam0_running,
                "pid": detection_cam0_process.pid if detection_cam0_running else None,
                "description": "카메라 0 모션 감지"
            },
            "cam1": {
                "running": detection_cam1_running,
                "pid": detection_cam1_process.pid if detection_cam1_running else None,
                "description": "카메라 1 모션 감지"
            },
            "both_running": detection_cam0_running and detection_cam1_running
        },
        "integration_controller": {
            "running": True,
            "port": 8080,
            "description": "통합 제어 시스템"
        }
    }

# FastAPI 라우트
@app.get("/")
async def root():
    """통합 제어판 메인 페이지"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>통합 제어 시스템</title>
        <meta charset="UTF-8">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 0; padding: 20px;
                background: #f5f5f5;
                min-height: 100vh;
            }
            .container {
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            h1 { 
                color: #333; 
                text-align: center; 
                margin-bottom: 30px;
                font-size: 28px;
            }
            .system-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                margin: 30px 0;
            }
            .system-card {
                border: 2px solid #dee2e6;
                border-radius: 10px;
                padding: 25px;
                background: #f8f9fa;
            }
            .system-card h2 {
                color: #495057;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .status-indicator {
                display: inline-block;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                margin-right: 8px;
            }
            .status-running {
                background: #28a745;
            }
            .status-stopped {
                background: #dc3545;
            }
            .status-disabled {
                background: #6c757d;
            }
            button {
                font-size: 14px;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                transition: all 0.3s;
                margin: 5px;
                min-width: 120px;
            }
            .btn-primary {
                background: #007bff;
                color: white;
            }
            .btn-primary:hover {
                background: #0056b3;
            }
            .btn-success {
                background: #28a745;
                color: white;
            }
            .btn-success:hover {
                background: #1e7e34;
            }
            .btn-danger {
                background: #dc3545;
                color: white;
            }
            .btn-danger:hover {
                background: #c82333;
            }
            .btn-secondary {
                background: #6c757d;
                color: white;
            }
            .btn-disabled {
                background: #6c757d;
                cursor: not-allowed;
            }
            .description {
                color: #6c757d;
                font-size: 14px;
                margin: 15px 0;
                line-height: 1.4;
            }
            .overall-status {
                text-align: center;
                margin: 20px 0;
                padding: 20px;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            .status-info {
                background: #d1ecf1;
                color: #0c5460;
                border: 1px solid #bee5eb;
            }
            .button-group {
                margin-top: 15px;
            }
            .access-link {
                display: inline-block;
                margin: 5px;
                padding: 8px 16px;
                background: #17a2b8;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                font-size: 13px;
                min-width: 100px;
                text-align: center;
            }
            .access-link:hover {
                background: #138496;
                text-decoration: none;
                color: white;
            }
            .access-link:disabled {
                background: #6c757d;
                cursor: not-allowed;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>라즈베리파이 통합 제어 시스템</h1>
            
            <div class="overall-status status-info" id="overall-status">
                시스템 상태 로딩 중...
            </div>
            
            <!-- 🚀 Phase 1: 자동 전환 버튼 섹션 -->
            <div style="text-align: center; margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border: 2px solid #007bff;">
                <h3 style="color: #007bff; margin-bottom: 15px;">🔄 스마트 모드 전환</h3>
                <button class="btn-primary" style="margin: 0 10px; padding: 12px 24px; font-size: 16px; font-weight: bold;" onclick="autoSwitchToCctv()">
                    🎥 CCTV 모드로 전환
                </button>
                <button class="btn-success" style="margin: 0 10px; padding: 12px 24px; font-size: 16px; font-weight: bold;" onclick="autoSwitchToDetection()">
                    🛡️ 모션 감지 모드로 전환
                </button>
                <div id="switch-status" style="margin-top: 10px; font-size: 14px; color: #6c757d;">
                    클릭 한 번으로 시스템 자동 전환
                </div>
            </div>
            
            <div class="system-grid">
                <!-- 기존 토글 스트리밍 -->
                <div class="system-card">
                    <h2>
                        토글 스트리밍 시스템
                        <span class="status-indicator" id="toggle-status"></span>
                    </h2>
                    
                    <div class="description">
                        picam2_main.py 시스템 <br>
                        카메라 0번 ↔ 카메라 1번 교차 스트리밍<br>
                        웹 UI로 카메라 토글 가능<br>
                        포트: 8001<br>
                        <strong>권장: 1개 클라이언트만 접속</strong>
                    </div>
                    
                    <div class="button-group">
                        <button class="btn-success" onclick="controlToggleStreaming('start')">
                            서비스 시작
                        </button>
                        <button class="btn-danger" onclick="controlToggleStreaming('stop')">
                            서비스 중지
                        </button>
                        <a href="#" target="_blank" class="access-link" id="streaming-link">
                            스트리밍 화면
                        </a>
                    </div>
                    
                    <div id="toggle-info" style="margin-top: 15px; font-size: 12px; color: #6c757d;">
                        상태: 확인 중...
                    </div>
                </div>
                
                <!-- 듀얼 모션 블랙박스 -->
                <div class="system-card">
                    <h2>
                        모션 감지 블랙박스
                        <span class="status-indicator" id="blackbox-status"></span>
                    </h2>
                    
                    <div class="description">
                        새로운 detection_cam 시스템<br>
                        <strong>카메라 0번, 1번 동시 모션 감지</strong><br>
                        모션 감지시 전후 총 30초 녹화(5+25 sec)<br>
                        자동 저장 관리 (7일 보관)<br>
                        백그라운드 자동 감시
                    </div>
                    
                    <div class="button-group">
                        <button class="btn-success" onclick="controlMotionBlackbox('start')">
                            시작
                        </button>
                        <button class="btn-danger" onclick="controlMotionBlackbox('stop')">
                            중지
                        </button>
                    </div>
                    
                    <div id="blackbox-info" style="margin-top: 15px; font-size: 12px; color: #6c757d;">
                        상태: 확인 중...
                    </div>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 40px; color: #6c757d;">
                <p><strong>시스템 구성:</strong></p>
                <p>토글 스트리밍: picam2_main.py (카메라 0↔1 교차)</p>
                <p>모션 감지 블랙박스: 새로운 기능 (카메라 0,1 동시 감지)</p>
                <p>독립 실행: 두 시스템은 서로 간섭 없이 동시 동작 가능</p>
                <p>주의사항: 토글 스트리밍은 1개 클라이언트만 접속 가능</p>
            </div>
        </div>
        
        <script>
            let statusInterval;
            
            function controlToggleStreaming(action) {
                const url = `/api/toggle-streaming/${action}`;
                
                fetch(url, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            console.log(`Toggle streaming ${action} success`);
                            updateStatus();
                        } else {
                            alert(`토글 스트리밍 ${action} 실패: ${data.message}`);
                        }
                    })
                    .catch(error => {
                        console.error('Toggle streaming control error:', error);
                        alert(`토글 스트리밍 제어 오류: ${error.message}`);
                    });
            }
            
            function controlMotionBlackbox(action) {
                const url = `/api/detection-systems/${action}`;
                
                fetch(url, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            console.log(`Detection systems ${action} success`);
                            updateStatus();
                        } else {
                            alert(`모션 감지 시스템 ${action} 실패: ${data.message}`);
                        }
                    })
                    .catch(error => {
                        console.error('Detection systems control error:', error);
                        alert(`모션 감지 시스템 제어 오류: ${error.message}`);
                    });
            }
            
            // 🚀 Phase 1: 자동 전환 함수들
            function autoSwitchToCctv() {
                document.getElementById('switch-status').textContent = '⏳ CCTV 모드로 전환 중...';
                document.getElementById('switch-status').style.color = '#007bff';
                
                fetch('/api/auto-switch-to-cctv', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            document.getElementById('switch-status').textContent = '✅ CCTV 모드 전환 완료! 잠시 후 CCTV 화면에 접속하세요.';
                            document.getElementById('switch-status').style.color = '#28a745';
                            
                            // 3초 후 CCTV 페이지로 리다이렉트
                            setTimeout(() => {
                                const cctvUrl = data.cctv_url || 'http://localhost:8001';
                                window.open(cctvUrl.replace('localhost', window.location.hostname), '_blank');
                            }, 3000);
                            
                            updateStatus();
                        } else {
                            document.getElementById('switch-status').textContent = `❌ 전환 실패: ${data.message}`;
                            document.getElementById('switch-status').style.color = '#dc3545';
                        }
                    })
                    .catch(error => {
                        console.error('Auto-switch to CCTV error:', error);
                        document.getElementById('switch-status').textContent = '❌ CCTV 전환 중 오류 발생';
                        document.getElementById('switch-status').style.color = '#dc3545';
                    });
            }
            
            function autoSwitchToDetection() {
                document.getElementById('switch-status').textContent = '⏳ 모션 감지 모드로 전환 중...';
                document.getElementById('switch-status').style.color = '#007bff';
                
                fetch('/api/auto-switch-to-detection', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            document.getElementById('switch-status').textContent = '✅ 모션 감지 모드 전환 완료! 자동 감시가 시작되었습니다.';
                            document.getElementById('switch-status').style.color = '#28a745';
                            updateStatus();
                        } else {
                            document.getElementById('switch-status').textContent = `❌ 전환 실패: ${data.message}`;
                            document.getElementById('switch-status').style.color = '#dc3545';
                        }
                    })
                    .catch(error => {
                        console.error('Auto-switch to detection error:', error);
                        document.getElementById('switch-status').textContent = '❌ 모션 감지 전환 중 오류 발생';
                        document.getElementById('switch-status').style.color = '#dc3545';
                    });
            }
            
            function updateStatus() {
                fetch('/api/status')
                    .then(response => response.json())
                    .then(data => {
                        // 토글 스트리밍 상태 및 링크 업데이트
                        const toggleStatus = document.getElementById('toggle-status');
                        const toggleInfo = document.getElementById('toggle-info');
                        const streamingLink = document.getElementById('streaming-link');
                        
                        if (data.toggle_streaming.running) {
                            toggleStatus.className = 'status-indicator status-running';
                            toggleInfo.innerHTML = `상태: 실행 중 (PID: ${data.toggle_streaming.pid})`;
                            streamingLink.href = `http://${window.location.hostname}:8001`;
                        } else {
                            toggleStatus.className = 'status-indicator status-stopped';
                            toggleInfo.innerHTML = '상태: 중지됨';
                            streamingLink.href = '#';
                        }
                        
                        // 모션 감지 시스템 상태
                        const blackboxStatus = document.getElementById('blackbox-status');
                        const blackboxInfo = document.getElementById('blackbox-info');
                        
                        const detectionSystems = data.detection_systems;
                        if (detectionSystems && detectionSystems.both_running) {
                            blackboxStatus.className = 'status-indicator status-running';
                            blackboxInfo.innerHTML = `상태: 실행 중 (Cam0: ${detectionSystems.cam0.pid}, Cam1: ${detectionSystems.cam1.pid})`;
                        } else if (detectionSystems && (detectionSystems.cam0.running || detectionSystems.cam1.running)) {
                            blackboxStatus.className = 'status-indicator status-running';
                            const runningCams = [];
                            if (detectionSystems.cam0.running) runningCams.push(`Cam0: ${detectionSystems.cam0.pid}`);
                            if (detectionSystems.cam1.running) runningCams.push(`Cam1: ${detectionSystems.cam1.pid}`);
                            blackboxInfo.innerHTML = `상태: 부분 실행 (${runningCams.join(', ')})`;
                        } else {
                            blackboxStatus.className = 'status-indicator status-stopped';
                            blackboxInfo.innerHTML = '상태: 중지됨';
                        }
                        
                        // 전체 상태
                        const overallStatus = document.getElementById('overall-status');
                        const runningServices = [];
                        
                        if (data.toggle_streaming.running) runningServices.push('토글 스트리밍');
                        if (detectionSystems && detectionSystems.both_running) {
                            runningServices.push('모션 감지 (양쪽 카메라)');
                        } else if (detectionSystems && (detectionSystems.cam0.running || detectionSystems.cam1.running)) {
                            runningServices.push('모션 감지 (일부 카메라)');
                        }
                        
                        if (runningServices.length > 0) {
                            overallStatus.textContent = `실행 중인 서비스: ${runningServices.join(', ')}`;
                        } else {
                            overallStatus.textContent = '모든 서비스 중지됨';
                        }
                    })
                    .catch(error => {
                        console.error('Status update error:', error);
                        document.getElementById('overall-status').textContent = '상태 업데이트 오류';
                    });
            }
            
            // 페이지 로드 시 상태 업데이트 시작
            document.addEventListener('DOMContentLoaded', function() {
                updateStatus(); // 즉시 한 번 실행
                statusInterval = setInterval(updateStatus, 3000); // 3초마다 업데이트
            });
            
            // 페이지 언로드 시 정리
            window.addEventListener('beforeunload', function() {
                if (statusInterval) clearInterval(statusInterval);
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/status")
async def get_status():
    """통합 시스템 상태 조회 API"""
    return JSONResponse(get_system_status())

@app.post("/api/toggle-streaming/{action}")
async def control_toggle_streaming(action: str):
    """토글 스트리밍 제어 API"""
    if action not in ["start", "stop"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'start' or 'stop'")
    
    try:
        if action == "start":
            success = start_toggle_streaming()
            message = "토글 스트리밍 시작됨" if success else "토글 스트리밍 시작 실패"
        else:
            success = stop_toggle_streaming()
            message = "토글 스트리밍 중지됨" if success else "토글 스트리밍 중지 실패"
        
        return {"success": success, "message": message}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Toggle streaming control error: {str(e)}")

@app.post("/api/detection-systems/{action}")
async def control_detection_systems(action: str):
    """모션 감지 시스템 제어 API"""
    if action not in ["start", "stop"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'start' or 'stop'")
    
    try:
        if action == "start":
            success = start_detection_systems()
            message = "모션 감지 시스템 시작됨" if success else "모션 감지 시스템 시작 실패"
        else:
            success = stop_detection_systems()
            message = "모션 감지 시스템 중지됨" if success else "모션 감지 시스템 중지 실패"
        
        return {"success": success, "message": message}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection systems control error: {str(e)}")

# 🚀 Phase 1: 자동 전환 API 추가
@app.post("/api/auto-switch-to-cctv")
async def auto_switch_to_cctv():
    """자동으로 detection 종료 후 CCTV 시작"""
    print("🔄 Auto-switching to CCTV mode...")
    
    try:
        # 1단계: detection 시스템 종료
        detection_stopped = stop_detection_systems()
        if not detection_stopped:
            return {"success": False, "message": "Detection 시스템 종료 실패"}
        
        # 잠시 대기 (프로세스 정리 시간)
        import asyncio
        await asyncio.sleep(2)
        
        # 2단계: CCTV 시스템 시작
        cctv_started = start_toggle_streaming()
        if not cctv_started:
            # 실패 시 detection 다시 시작
            start_detection_systems()
            return {"success": False, "message": "CCTV 시스템 시작 실패"}
        
        print("✅ Successfully switched to CCTV mode")
        return {
            "success": True, 
            "mode": "cctv",
            "message": "CCTV 모드로 전환 완료",
            "cctv_url": "http://localhost:8001"
        }
    
    except Exception as e:
        print(f"❌ Auto-switch to CCTV error: {e}")
        # 오류 시 detection 다시 시작 시도
        start_detection_systems()
        raise HTTPException(status_code=500, detail=f"Auto-switch error: {str(e)}")

@app.post("/api/auto-switch-to-detection")  
async def auto_switch_to_detection():
    """자동으로 CCTV 종료 후 detection 시작"""
    print("🔄 Auto-switching to detection mode...")
    
    try:
        # 1단계: CCTV 시스템 종료
        cctv_stopped = stop_toggle_streaming()
        if not cctv_stopped:
            return {"success": False, "message": "CCTV 시스템 종료 실패"}
        
        # 잠시 대기 (프로세스 정리 시간)
        import asyncio
        await asyncio.sleep(2)
        
        # 2단계: detection 시스템 시작
        detection_started = start_detection_systems()
        if not detection_started:
            return {"success": False, "message": "Detection 시스템 시작 실패"}
        
        print("✅ Successfully switched to detection mode")
        return {
            "success": True,
            "mode": "detection", 
            "message": "모션 감지 모드로 전환 완료"
        }
    
    except Exception as e:
        print(f"❌ Auto-switch to detection error: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-switch error: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 초기 설정"""
    print("🚀 통합 제어 시스템 시작")
    print("   토글 스트리밍 (picam2_main.py) + 모션 감지 시스템 (detection_cam0.py, detection_cam1.py)")
    
    # 기본적으로 detection 시스템만 자동 시작
    print("🛡️ 모션 감지 시스템 자동 시작...")
    start_detection_systems()

@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 모든 프로세스 정리"""
    print("🧹 모든 서비스 정리 중...")
    stop_toggle_streaming()
    stop_detection_systems()

if __name__ == "__main__":
    print("🚀 Starting integrated controller on port 8080")
    print("🎯 Control panel: http://<your-pi-ip>:8080")
    print("📹 Toggle streaming: http://<your-pi-ip>:8001 (when started)")
    print("")
    print("🔄 서비스 구성:")
    print("   • 통합 제어: 포트 8080 (이 서버)")
    print("   • 토글 스트리밍: 포트 8001 (picam2_main.py - 1 클라이언트 권장)")
    print("   • 모션 블랙박스: 백그라운드 (detection_cam0,1.py 듀얼 카메라 동시 감지)")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )