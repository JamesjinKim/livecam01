#!/usr/bin/env python3
"""
간단한 카메라 0번 연속 녹화 시스템
30초씩 MP4 파일을 연속으로 저장하는 단순한 레코더

Author: Assistant
Date: 2025-09-05
"""

import subprocess
import time
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

class SimpleRecorder:
    def __init__(self, camera_id=0, duration=31, resolution="640x480"):
        """
        Simple MP4 recorder
        
        Args:
            camera_id (int): 카메라 번호 (0 또는 1)
            duration (int): 녹화 시간 (초)
            resolution (str): 해상도 "WIDTHxHEIGHT"
        """
        self.camera_id = camera_id
        self.duration = duration * 1000  # rpicam-vid는 밀리초 단위
        self.width, self.height = map(int, resolution.split('x'))
        
        # 저장 디렉토리 설정
        self.base_dir = Path("videos/simple_rec/cam0")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 현재 녹화 프로세스 및 파일
        self.current_process = None
        self.current_file = None
        
        # 종료 신호 처리
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        print(f"🎥 간단한 카메라 {camera_id}번 연속 녹화 시스템")
        print(f"   해상도: {resolution}")
        print(f"   녹화 길이: {duration}초 (실제 영상: 30초)")
        print(f"   저장 경로: {self.base_dir}")
        print()

    def _signal_handler(self, signum, frame):
        """종료 신호 처리"""
        print("\n🛑 종료 신호 수신")
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        """현재 프로세스 정리 및 미완성 파일 삭제"""
        if self.current_process and self.current_process.poll() is None:
            print("⏹️ 현재 녹화 중지 중...")
            try:
                # 프로세스 그룹 전체 종료
                os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                self.current_process.wait(timeout=5)
            except:
                # 강제 종료
                try:
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                except:
                    pass
            print("✅ 녹화 중지 완료")
        
        # 미완성 파일 삭제
        if self.current_file and self.current_file.exists():
            try:
                file_size = self.current_file.stat().st_size
                self.current_file.unlink()
                print(f"🗑️  미완성 파일 삭제: {self.current_file.name} ({file_size/1024/1024:.1f}MB)")
            except Exception as e:
                print(f"⚠️  파일 삭제 실패: {str(e)}")
        
        self.current_process = None
        self.current_file = None

    def _generate_filename(self):
        """파일명 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.base_dir / f"rec_cam{self.camera_id}_{timestamp}.mp4"

    def _record_video(self, output_path):
        """단일 비디오 녹화"""
        cmd = [
            "rpicam-vid",
            f"--camera", str(self.camera_id),
            f"--width", str(self.width),
            f"--height", str(self.height),
            f"--timeout", str(self.duration),
            f"--output", str(output_path),
            "--nopreview",
            "--codec", "h264",
            "--framerate", "30"
        ]
        
        start_time = datetime.now().strftime("%H:%M:%S")
        print(f"[{start_time}] 🎬 녹화 시작: {output_path.name}")
        
        # 현재 파일 추적
        self.current_file = output_path
        
        try:
            # 프로세스 그룹으로 실행
            self.current_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            # 녹화 완료 대기
            self.current_process.wait()
            
            if self.current_process.returncode == 0:
                # 파일 크기 확인
                if output_path.exists():
                    file_size = output_path.stat().st_size
                    size_mb = file_size / (1024 * 1024)
                    end_time = datetime.now().strftime("%H:%M:%S")
                    print(f"[{end_time}] ✅ 녹화 완료: {output_path.name} ({size_mb:.1f}MB)")
                    # 완료된 파일은 추적 해제
                    self.current_file = None
                    return True
                else:
                    end_time = datetime.now().strftime("%H:%M:%S")
                    print(f"[{end_time}] ❌ 파일 생성 실패: {output_path.name}")
                    return False
            else:
                end_time = datetime.now().strftime("%H:%M:%S")
                print(f"[{end_time}] ❌ 녹화 실패 (코드: {self.current_process.returncode})")
                return False
                
        except Exception as e:
            end_time = datetime.now().strftime("%H:%M:%S")
            print(f"[{end_time}] ❌ 녹화 오류: {str(e)}")
            return False
        finally:
            self.current_process = None

    def start_continuous_recording(self):
        """연속 녹화 시작"""
        print("🚀 연속 녹화 시작 (Ctrl+C로 종료)")
        print("=" * 50)
        
        recording_count = 0
        
        try:
            while True:
                recording_count += 1
                
                # 파일명 생성
                output_path = self._generate_filename()
                
                # 녹화 실행
                success = self._record_video(output_path)
                
                if success:
                    print(f"📊 완료된 녹화: {recording_count}개")
                else:
                    print(f"⚠️  실패한 녹화: {recording_count}번째")
                
                # 잠시 대기 (프로세스 정리 시간)
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 사용자가 종료 요청")
            self._cleanup()
        except Exception as e:
            print(f"\n❌ 예상치 못한 오류: {str(e)}")
            self._cleanup()
        
        print(f"\n📋 총 {recording_count}개 파일 녹화 완료")
        print("👋 녹화 시스템 종료")


def main():
    """메인 함수"""
    print("🎯 간단한 연속 MP4 녹화 시스템")
    print("=" * 40)
    
    # 카메라 확인
    print("📹 카메라 0번 확인 중...")
    
    try:
        # 간단한 카메라 테스트
        test_cmd = ["rpicam-hello", "--camera", "0", "--timeout", "1000"]
        result = subprocess.run(test_cmd, capture_output=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ 카메라 0번 정상")
        else:
            print("❌ 카메라 0번 오류")
            print("stderr:", result.stderr.decode())
            return
            
    except Exception as e:
        print(f"❌ 카메라 테스트 실패: {str(e)}")
        return
    
    # 레코더 시작
    recorder = SimpleRecorder(camera_id=0, duration=31, resolution="640x480")
    recorder.start_continuous_recording()


if __name__ == "__main__":
    main()