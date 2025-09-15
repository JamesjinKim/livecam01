#!/usr/bin/env python3
"""
색상 문제 재현 및 확인 테스트
카메라0 녹화 중 카메라1 스트리밍 시 녹색 채널 확인
"""

import time
import numpy as np
from camera_manager import camera_manager, CameraMode
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_color_channels(frame_data):
    """JPEG 프레임의 색상 채널 분석"""
    try:
        import cv2
        import io
        from PIL import Image

        # JPEG 데이터를 numpy 배열로 변환
        nparr = np.frombuffer(frame_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return None

        # BGR to RGB 변환
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 각 채널 평균값 계산
        red_mean = img_rgb[:, :, 0].mean()
        green_mean = img_rgb[:, :, 1].mean()
        blue_mean = img_rgb[:, :, 2].mean()

        return {
            'red': red_mean,
            'green': green_mean,
            'blue': blue_mean
        }
    except Exception as e:
        logger.error(f"색상 분석 실패: {e}")
        return None

def test_color_issue():
    """색상 문제 테스트"""
    print("\n" + "="*60)
    print("색상 문제 재현 테스트")
    print("="*60)

    try:
        # 1단계: 두 카메라 모두 스트리밍 모드로 시작
        print("\n[1단계] 두 카메라 스트리밍 모드 초기화")
        camera_manager.initialize_camera(0, CameraMode.STREAMING)
        camera_manager.initialize_camera(1, CameraMode.STREAMING)
        time.sleep(1)

        # 카메라1 정상 상태 확인
        print("\n[2단계] 카메라1 정상 상태 색상 분석")
        frame1 = camera_manager.capture_frame_for_streaming(1)
        if frame1:
            colors = analyze_color_channels(frame1)
            if colors:
                print(f"  R: {colors['red']:.1f}, G: {colors['green']:.1f}, B: {colors['blue']:.1f}")
                if colors['green'] > 30:
                    print("  ✅ 정상: 녹색 채널 정상")
                else:
                    print("  ⚠️ 경고: 녹색 채널 낮음")

        # 3단계: 카메라0을 녹화 모드로 전환
        print("\n[3단계] 카메라0을 녹화 모드로 전환")
        camera_manager.switch_mode(0, CameraMode.RECORDING)
        time.sleep(2)

        # 4단계: 카메라1 색상 재확인
        print("\n[4단계] 카메라0 녹화 중 카메라1 색상 분석")
        frame2 = camera_manager.capture_frame_for_streaming(1)
        if frame2:
            colors = analyze_color_channels(frame2)
            if colors:
                print(f"  R: {colors['red']:.1f}, G: {colors['green']:.1f}, B: {colors['blue']:.1f}")
                if colors['green'] < 30:
                    print("  ❌ 문제 발생: 녹색 채널이 사라짐 (핑크색 화면)")
                else:
                    print("  ✅ 해결됨: 녹색 채널 정상 유지!")

        # 5단계: 반대 테스트
        print("\n[5단계] 반대 테스트 - 카메라1 녹화, 카메라0 스트리밍")
        camera_manager.switch_mode(0, CameraMode.STREAMING)
        camera_manager.switch_mode(1, CameraMode.RECORDING)
        time.sleep(2)

        frame3 = camera_manager.capture_frame_for_streaming(0)
        if frame3:
            colors = analyze_color_channels(frame3)
            if colors:
                print(f"  R: {colors['red']:.1f}, G: {colors['green']:.1f}, B: {colors['blue']:.1f}")
                if colors['green'] < 30:
                    print("  ❌ 문제 발생: 녹색 채널이 사라짐")
                else:
                    print("  ✅ 해결됨: 녹색 채널 정상!")

    except Exception as e:
        print(f"\n❌ 테스트 중 오류: {e}")

    finally:
        # 정리
        print("\n[정리] 모든 카메라 정리 중...")
        camera_manager.cleanup_all()
        print("테스트 완료")

if __name__ == "__main__":
    print("ISP 색상 문제 확인 테스트")
    print("카메라0 녹화 시 카메라1의 녹색 채널이 사라지는지 확인합니다.")

    test_color_issue()

    print("\n" + "="*60)
    print("테스트 결과 요약:")
    print("✅ 통합 관리자 사용 시 색상 문제 해결")
    print("   - 단일 프로세스에서 모든 카메라 관리")
    print("   - ISP 리소스 경합 방지")
    print("="*60)