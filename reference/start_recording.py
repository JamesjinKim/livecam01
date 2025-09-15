#!/usr/bin/env python3
"""
스트리밍과 녹화 동기화 스크립트
스트리밍 중인 경우 일시 정지 후 녹화 시작
"""

import subprocess
import time
import sys
import signal
import requests
import argparse

def check_streaming_status():
    """스트리밍 상태 확인"""
    try:
        response = requests.get("http://localhost:8001/api/stats", timeout=1)
        if response.status_code == 200:
            data = response.json()
            return data.get("active_clients", 0) > 0
    except:
        return False

def pause_streaming():
    """스트리밍 일시 정지"""
    try:
        # 듀얼 모드 비활성화로 리소스 확보
        requests.post("http://localhost:8001/api/dual_mode/false")
        time.sleep(0.5)
        return True
    except:
        return False

def start_recording(camera_id):
    """녹화 시작"""
    script = f"rec_cam{camera_id}.py"
    try:
        # 녹화 프로세스 시작
        process = subprocess.Popen(
            ["python3", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return process
    except Exception as e:
        print(f"[ERROR] 녹화 시작 실패: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="동기화된 녹화 시작")
    parser.add_argument("camera", type=int, choices=[0, 1], help="카메라 번호 (0 또는 1)")
    parser.add_argument("--no-sync", action="store_true", help="동기화 없이 바로 시작")
    args = parser.parse_args()

    print(f"[INFO] 카메라 {args.camera} 녹화 준비 중...")

    if not args.no_sync:
        # 스트리밍 상태 확인
        if check_streaming_status():
            print("[INFO] 스트리밍 감지됨, 리소스 최적화 중...")
            if pause_streaming():
                print("[OK] 스트리밍 리소스 확보 완료")
                time.sleep(0.5)

    # 녹화 시작
    print(f"[START] 카메라 {args.camera} 녹화 시작...")
    process = start_recording(args.camera)

    if process:
        try:
            # 녹화 프로세스 대기
            process.wait()
        except KeyboardInterrupt:
            print("\n[STOP] 녹화 중단 요청...")
            process.terminate()
            process.wait()
            print("[OK] 녹화 종료됨")
    else:
        print("[ERROR] 녹화 시작 실패")
        sys.exit(1)

if __name__ == "__main__":
    main()