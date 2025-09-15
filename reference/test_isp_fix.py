#!/usr/bin/env python3
"""
ISP 리소스 경합 문제 테스트 스크립트
색상 문제가 발생하는지 확인
"""

import time
import subprocess
import sys
from pathlib import Path

def test_scenario_1():
    """시나리오 1: 카메라0 녹화 중 카메라1 스트리밍"""
    print("\n[TEST 1] 카메라0 녹화 + 카메라1 스트리밍")
    print("=" * 50)

    # 카메라0 녹화 시작
    print("1. 카메라0 녹화 시작...")
    rec0 = subprocess.Popen(["python3", "rec_cam0.py"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    time.sleep(3)

    # 카메라1을 간단히 테스트
    print("2. 카메라1 캡처 테스트...")
    try:
        from picamera2 import Picamera2
        picam1 = Picamera2(camera_num=1)
        config = picam1.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        picam1.configure(config)
        picam1.start()

        # 프레임 캡처
        array = picam1.capture_array()
        print(f"   캡처된 이미지 shape: {array.shape}")

        # 색상 체크 (녹색 채널)
        green_channel = array[:, :, 1]  # RGB의 G 채널
        green_mean = green_channel.mean()
        print(f"   녹색 채널 평균값: {green_mean:.1f}")

        if green_mean < 30:
            print("   ⚠️  경고: 녹색 채널이 매우 낮음 (핑크색 화면 가능성)")
        else:
            print("   ✓ 정상: 녹색 채널 정상")

        picam1.stop()
        picam1.close()

    except Exception as e:
        print(f"   ❌ 오류: {e}")

    # 녹화 중지
    rec0.terminate()
    rec0.wait()
    print("3. 카메라0 녹화 중지")

def test_scenario_2():
    """시나리오 2: 통합 관리자 테스트"""
    print("\n[TEST 2] 통합 카메라 관리자 테스트")
    print("=" * 50)

    try:
        from camera_manager import camera_manager, CameraMode

        # 카메라0 녹화 모드
        print("1. 카메라0을 녹화 모드로 설정...")
        success = camera_manager.initialize_camera(0, CameraMode.RECORDING)
        print(f"   결과: {'✓ 성공' if success else '❌ 실패'}")

        time.sleep(2)

        # 카메라1 스트리밍 모드
        print("2. 카메라1을 스트리밍 모드로 설정...")
        success = camera_manager.initialize_camera(1, CameraMode.STREAMING)
        print(f"   결과: {'✓ 성공' if success else '❌ 실패'}")

        # 프레임 캡처 테스트
        print("3. 카메라1에서 프레임 캡처...")
        frame = camera_manager.capture_frame_for_streaming(1)
        if frame:
            print(f"   ✓ 프레임 캡처 성공 ({len(frame)} bytes)")
        else:
            print("   ❌ 프레임 캡처 실패")

        # 정리
        camera_manager.cleanup_all()
        print("4. 정리 완료")

    except Exception as e:
        print(f"오류 발생: {e}")

def main():
    print("ISP 리소스 경합 문제 테스트")
    print("=" * 60)

    choice = input("\n테스트 선택:\n1. 기본 테스트 (rec_cam0.py 사용)\n2. 통합 관리자 테스트\n3. 모두 테스트\n선택 [1/2/3]: ")

    if choice == "1":
        test_scenario_1()
    elif choice == "2":
        test_scenario_2()
    elif choice == "3":
        test_scenario_1()
        test_scenario_2()
    else:
        print("잘못된 선택")

    print("\n테스트 완료")

if __name__ == "__main__":
    main()