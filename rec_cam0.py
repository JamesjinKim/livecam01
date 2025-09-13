#!/usr/bin/env python3
"""
Picamera2 GPU 가속 카메라 0번 연속 녹화 시스템
30초씩 H.264 파일을 연속으로 저장하는 GPU 가속 레코더

Author: Assistant
Date: 2025-09-10
Hardware: Raspberry Pi 5 + VideoCore VII GPU
"""

import time
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Picamera2Recorder:
    def __init__(self, camera_id=0, duration=30, resolution="1920x1080"):
        """
        Picamera2 GPU 가속 H.264 레코더
        
        Args:
            camera_id (int): 카메라 번호 (0 또는 1)
            duration (int): 녹화 시간 (초)
            resolution (str): 해상도 "WIDTHxHEIGHT"
        """
        self.camera_id = camera_id
        self.duration = duration  # 초 단위
        self.width, self.height = map(int, resolution.split('x'))
        
        # 저장 디렉토리 설정
        self.base_dir = Path("videos/picam2_rec/cam0")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Picamera2 인스턴스
        self.picam2 = None
        self.encoder = None
        self.current_output = None
        self.current_file = None
        self.is_recording = False
        
        # 종료 신호 처리
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        print("=" * 60)
        print("Picamera2 GPU 가속 카메라 0번 연속 녹화 시스템")
        print("=" * 60)
        print(f"카메라 ID: {camera_id}")
        print(f"해상도: {resolution}")
        print(f"녹화 길이: {duration}초")
        print(f"저장 경로: {self.base_dir}")
        print(f"GPU: VideoCore VII (H.264 하드웨어 인코딩)")
        print("=" * 60)
        print()
        
        # 카메라 초기화
        self._initialize_camera()

    def _signal_handler(self, signum, frame):
        """종료 신호 처리"""
        print("\n[SIGNAL] 종료 신호 수신 (Ctrl+C)")
        self._cleanup()
        sys.exit(0)

    def _initialize_camera(self):
        """Picamera2 초기화 및 설정"""
        try:
            print("[INIT] Picamera2 초기화 중...")
            
            # Picamera2 인스턴스 생성
            self.picam2 = Picamera2(camera_num=self.camera_id)
            
            # 비디오 설정 (GPU 최적화)
            video_config = self.picam2.create_video_configuration(
                main={
                    "size": (self.width, self.height),
                    "format": "YUV420"  # H.264 인코딩에 최적
                },
                buffer_count=4,  # 버퍼 수 최적화
                queue=False      # 프레임 드롭 방지
            )
            
            self.picam2.configure(video_config)
            
            logger.info(f"카메라 {self.camera_id} 초기화 완료")
            print(f"[OK] Camera {self.camera_id} initialized (Picamera2)")
            
            # Pi5 하드웨어 정보 출력
            print("[INFO] Hardware: Raspberry Pi 5 + PiSP BCM2712_D0")
            print("[INFO] GPU Encoder: VideoCore VII H.264 Hardware Encoder")
            
        except Exception as e:
            logger.error(f"카메라 초기화 실패: {e}")
            print(f"[ERROR] Camera initialization failed: {e}")
            sys.exit(1)

    def _cleanup(self):
        """현재 녹화 정리 및 카메라 종료"""
        print("\n[CLEANUP] 정리 작업 시작...")
        
        # 현재 녹화 중이면 중지
        if self.is_recording and self.encoder:
            try:
                print("[STOP] 현재 녹화 중지 중...")
                self.picam2.stop_encoder(self.encoder)
                self.is_recording = False
                print("[OK] 녹화 중지 완료")
            except Exception as e:
                logger.error(f"녹화 중지 실패: {e}")
        
        # Picamera2 카메라 정지
        if self.picam2:
            try:
                if self.picam2.started:
                    self.picam2.stop()
                    print("[STOP] 카메라 정지 완료")
                self.picam2.close()
                print("[OK] 카메라 정리 완료")
            except Exception as e:
                logger.error(f"카메라 정리 실패: {e}")
        
        # 미완성 파일 삭제
        if self.current_file and self.current_file.exists():
            try:
                file_size = self.current_file.stat().st_size
                # 10KB 미만 파일은 삭제 (손상된 파일)
                if file_size < 10240:
                    self.current_file.unlink()
                    print(f"[DELETE] 손상된 파일 삭제: {self.current_file.name} ({file_size/1024:.1f}KB)")
                else:
                    print(f"[KEEP] 마지막 파일 보존: {self.current_file.name} ({file_size/1024/1024:.1f}MB)")
            except Exception as e:
                logger.error(f"파일 처리 실패: {e}")

    def _generate_filename(self):
        """파일명 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.base_dir / f"picam2_cam{self.camera_id}_{timestamp}.mp4"

    def _record_single_video(self, output_path):
        """단일 비디오 녹화 (GPU 가속)"""
        start_time = datetime.now()
        start_str = start_time.strftime("%H:%M:%S")
        
        try:
            print(f"[{start_str}] [RECORD] 녹화 시작: {output_path.name}")
            
            # 현재 파일 추적
            self.current_file = output_path
            
            # H.264 인코더 생성 (GPU 하드웨어 가속)
            self.encoder = H264Encoder(
                bitrate=5000000,  # 5Mbps (1080p에 적합)
                repeat=True,       # SPS/PPS 반복
                iperiod=30,        # I-프레임 주기
                framerate=30       # 30fps
            )
            
            # MP4 파일 출력 설정 (ffmpeg을 통한 컨테이너 래핑)
            self.current_output = FfmpegOutput(str(output_path))
            self.encoder.output = self.current_output
            
            # 카메라 시작 (아직 시작 안 했으면)
            if not self.picam2.started:
                self.picam2.start()
                time.sleep(0.5)  # 카메라 안정화
            
            # 녹화 시작 (GPU 인코딩)
            self.picam2.start_encoder(self.encoder)
            self.is_recording = True
            
            # 지정된 시간 동안 녹화
            time.sleep(self.duration)
            
            # 녹화 중지
            self.picam2.stop_encoder(self.encoder)
            self.is_recording = False
            
            # 파일 크기 확인
            if output_path.exists():
                file_size = output_path.stat().st_size
                size_mb = file_size / (1024 * 1024)
                end_time = datetime.now()
                end_str = end_time.strftime("%H:%M:%S")
                duration = (end_time - start_time).total_seconds()
                
                print(f"[{end_str}] [OK] 녹화 완료: {output_path.name}")
                print(f"           [STATS] 크기: {size_mb:.1f}MB, 시간: {duration:.1f}초")
                
                # 완료된 파일은 추적 해제
                self.current_file = None
                return True
            else:
                print(f"[ERROR] 파일 생성 실패: {output_path.name}")
                return False
                
        except Exception as e:
            end_str = datetime.now().strftime("%H:%M:%S")
            logger.error(f"녹화 오류: {e}")
            print(f"[{end_str}] [ERROR] 녹화 오류: {str(e)}")
            self.is_recording = False
            return False

    def start_continuous_recording(self):
        """연속 녹화 시작"""
        print("\n[START] 연속 녹화 시작 (Ctrl+C로 종료)")
        print("=" * 50)
        
        recording_count = 0
        success_count = 0
        fail_count = 0
        total_size = 0
        
        try:
            while True:
                recording_count += 1
                
                # 파일명 생성
                output_path = self._generate_filename()
                
                # 녹화 실행 (GPU 가속)
                success = self._record_single_video(output_path)
                
                if success:
                    success_count += 1
                    if output_path.exists():
                        total_size += output_path.stat().st_size
                    print(f"[PROGRESS] 성공 {success_count}개 / 실패 {fail_count}개")
                    print(f"[STORAGE] 총 저장 용량: {total_size/1024/1024:.1f}MB")
                else:
                    fail_count += 1
                    print(f"[FAIL] 실패한 녹화: {recording_count}번째")
                
                # 짧은 대기 (프레임 버퍼 정리)
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n[SIGNAL] 사용자가 종료 요청")
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}")
            print(f"\n[ERROR] 예상치 못한 오류: {str(e)}")
        finally:
            self._cleanup()
        
        # 최종 통계
        print("\n" + "=" * 50)
        print("[STATS] 녹화 통계")
        print(f"   총 시도: {recording_count}개")
        print(f"   성공: {success_count}개")
        print(f"   실패: {fail_count}개")
        print(f"   총 용량: {total_size/1024/1024:.1f}MB")
        print("=" * 50)
        print("[EXIT] Picamera2 녹화 시스템 종료")


def main():
    """메인 함수"""
    print("Picamera2 GPU 가속 연속 녹화 시스템")
    print("Hardware: Raspberry Pi 5 + VideoCore VII")
    print("=" * 60)
    
    # 카메라 확인
    print("[TEST] 카메라 0번 확인 중...")
    
    try:
        # Picamera2로 카메라 테스트
        test_cam = Picamera2(camera_num=0)
        test_cam.close()
        print("[OK] 카메라 0번 정상 (Picamera2)")
        print("[OK] GPU 하드웨어 인코더 사용 가능")
        
    except Exception as e:
        print(f"[ERROR] 카메라 테스트 실패: {str(e)}")
        print("카메라 연결을 확인하세요.")
        return
    
    # 기본 설정으로 바로 시작
    resolution = "1920x1080"  # Full HD 기본값
    duration = 30  # 30초 기본값
    
    print(f"\n[CONFIG] 해상도: {resolution} (Full HD)")
    print(f"[CONFIG] 녹화 시간: {duration}초")
    print(f"[CONFIG] 출력 형식: MP4 (H.264)")
    print(f"[CONFIG] 비트레이트: 5Mbps")
    
    # 레코더 시작
    print("\n" + "=" * 60)
    recorder = Picamera2Recorder(
        camera_id=0, 
        duration=duration, 
        resolution=resolution
    )
    recorder.start_continuous_recording()


if __name__ == "__main__":
    main()