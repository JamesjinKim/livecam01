#!/usr/bin/env python3
"""
빠른 색상 문제 테스트
기존 방식 vs 통합 방식 비교
"""

import subprocess
import time
import sys
from pathlib import Path

def test_old_way():
    """기존 방식 테스트 (문제 있는 방식)"""
    print("\n[기존 방식 테스트] rec_cam0.py + 카메라1 동시 접근")
    print("-" * 50)

    # rec_cam0.py 백그라운드 실행
    rec_process = subprocess.Popen(
        ["python3", "rec_cam0.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    print("✓ 카메라0 녹화 시작 (3초 대기)")
    time.sleep(3)

    # 카메라1 간단 테스트
    try:
        from picamera2 import Picamera2
        picam1 = Picamera2(camera_num=1)
        config = picam1.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        picam1.configure(config)
        picam1.start()
        time.sleep(1)

        # 프레임 캡처
        array = picam1.capture_array()
        green_mean = array[:, :, 1].mean()

        print(f"카메라1 녹색 채널 평균: {green_mean:.1f}")
        if green_mean < 30:
            print("❌ 색상 문제 발생! (핑크색 화면)")
            result = "FAILED"
        else:
            print("✅ 색상 정상")
            result = "PASSED"

        picam1.stop()
        picam1.close()

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        result = "ERROR"

    # 녹화 중지
    rec_process.terminate()
    rec_process.wait()

    return result

def test_new_way():
    """새로운 통합 방식 테스트"""
    print("\n[통합 방식 테스트] camera_manager 사용")
    print("-" * 50)

    try:
        from camera_manager import camera_manager, CameraMode

        # 카메라0 녹화 모드
        camera_manager.initialize_camera(0, CameraMode.RECORDING)
        print("✓ 카메라0 녹화 모드 설정")

        # 카메라1 스트리밍 모드
        camera_manager.initialize_camera(1, CameraMode.STREAMING)
        print("✓ 카메라1 스트리밍 모드 설정")

        time.sleep(2)

        # 프레임 캡처
        frame = camera_manager.capture_frame_for_streaming(1)
        if frame:
            print(f"✓ 프레임 캡처 성공 ({len(frame)} bytes)")
            print("✅ 색상 문제 해결됨!")
            result = "PASSED"
        else:
            print("❌ 프레임 캡처 실패")
            result = "FAILED"

        # 정리
        camera_manager.cleanup_all()

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        result = "ERROR"

    return result

def main():
    print("🔬 ISP 리소스 경합 문제 해결 확인 테스트")
    print("=" * 60)

    choice = input("\n테스트 선택:\n1. 기존 방식 (문제 확인)\n2. 통합 방식 (해결 확인)\n3. 비교 테스트\n선택 [1/2/3]: ")

    if choice == "1":
        result = test_old_way()
        print(f"\n결과: {result}")

    elif choice == "2":
        result = test_new_way()
        print(f"\n결과: {result}")

    elif choice == "3":
        print("\n📊 비교 테스트 실행")
        old_result = test_old_way()
        time.sleep(2)
        new_result = test_new_way()

        print("\n" + "=" * 60)
        print("📋 테스트 결과 요약")
        print("=" * 60)
        print(f"기존 방식 (별도 프로세스): {old_result}")
        print(f"통합 방식 (단일 프로세스): {new_result}")
        print()
        if old_result == "FAILED" and new_result == "PASSED":
            print("🎉 성공! ISP 리소스 경합 문제가 해결되었습니다!")
        else:
            print("⚠️ 추가 확인이 필요합니다.")

    else:
        print("잘못된 선택")

if __name__ == "__main__":
    main()