"""
SHT 듀얼 LIVE 카메라 - 설정 관리자
Configuration Manager for CCTV System
"""

import json
import os
import logging
from typing import Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigManager:
    """설정 파일 관리자"""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = {}
        self.default_config = self._get_default_config()
        self.load_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정값 반환"""
        return {
            "recording": {
                "enabled": True,
                "segment_duration": 31,
                "overlap_duration": 1,
                "bitrate": 5000000,
                "framerate": 30,
                "resolution": [640, 480],
                "cameras": {
                    "0": {
                        "enabled": True,
                        "storage_path": "videos/cam0"
                    },
                    "1": {
                        "enabled": True,
                        "storage_path": "videos/cam1"
                    }
                },
                "cleanup": {
                    "enabled": False,
                    "max_age_days": 30,
                    "min_free_space_gb": 10
                }
            },
            "streaming": {
                "max_clients": 2,
                "default_quality": "640x480",
                "mirror_mode": True,
                "buffer_size": 10,
                "stats_interval": 2000,
                "heartbeat_interval": 3000
            },
            "system": {
                "web_port": 8001,
                "log_level": "INFO",
                "gpu_memory_split": 256
            }
        }

    def load_config(self) -> bool:
        """설정 파일 로드"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info(f"[CONFIG] 설정 파일 로드 완료: {self.config_path}")

                # 누락된 설정값을 기본값으로 채움
                self._merge_default_config()
                return True
            else:
                logger.warning(f"[CONFIG] 설정 파일이 없습니다. 기본값 사용: {self.config_path}")
                self.config = self.default_config.copy()
                self.save_config()
                return False

        except Exception as e:
            logger.error(f"[CONFIG] 설정 파일 로드 실패: {e}")
            self.config = self.default_config.copy()
            return False

    def _merge_default_config(self):
        """기본 설정과 로드된 설정 병합"""
        def merge_dict(default: dict, loaded: dict) -> dict:
            result = default.copy()
            for key, value in loaded.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge_dict(result[key], value)
                else:
                    result[key] = value
            return result

        self.config = merge_dict(self.default_config, self.config)

    def save_config(self) -> bool:
        """설정 파일 저장"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"[CONFIG] 설정 파일 저장 완료: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"[CONFIG] 설정 파일 저장 실패: {e}")
            return False

    def get(self, path: str, default=None) -> Any:
        """설정값 조회 (점 표기법 지원)
        예: get('recording.bitrate') -> 5000000
        """
        keys = path.split('.')
        value = self.config

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, path: str, value: Any) -> bool:
        """설정값 변경 (점 표기법 지원)
        예: set('recording.bitrate', 8000000)
        """
        keys = path.split('.')
        config = self.config

        try:
            # 마지막 키를 제외하고 경로 생성
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]

            # 마지막 키에 값 설정
            config[keys[-1]] = value
            return True
        except Exception as e:
            logger.error(f"[CONFIG] 설정값 변경 실패 {path}={value}: {e}")
            return False

    def reload(self) -> bool:
        """설정 파일 다시 로드"""
        logger.info("[CONFIG] 설정 파일 다시 로드")
        return self.load_config()

    # 편의 메서드들
    def get_recording_config(self) -> Dict[str, Any]:
        """녹화 설정 반환"""
        return self.get('recording', {})

    def get_streaming_config(self) -> Dict[str, Any]:
        """스트리밍 설정 반환"""
        return self.get('streaming', {})

    def get_system_config(self) -> Dict[str, Any]:
        """시스템 설정 반환"""
        return self.get('system', {})

    def get_camera_config(self, camera_id: str) -> Dict[str, Any]:
        """특정 카메라 설정 반환"""
        return self.get(f'recording.cameras.{camera_id}', {})

    def get_resolution(self) -> Tuple[int, int]:
        """해상도 반환"""
        resolution = self.get('recording.resolution', [640, 480])
        return tuple(resolution)

    def get_segment_duration(self) -> int:
        """세그먼트 길이 반환"""
        return self.get('recording.segment_duration', 31)

    def get_bitrate(self) -> int:
        """비트레이트 반환"""
        return self.get('recording.bitrate', 5000000)

    def get_framerate(self) -> int:
        """프레임레이트 반환"""
        return self.get('recording.framerate', 30)

    def get_max_clients(self) -> int:
        """최대 클라이언트 수 반환"""
        return self.get('streaming.max_clients', 2)

    def get_web_port(self) -> int:
        """웹 서버 포트 반환"""
        return self.get('system.web_port', 8001)

    def is_camera_enabled(self, camera_id: str) -> bool:
        """카메라 활성화 여부 확인"""
        return self.get(f'recording.cameras.{camera_id}.enabled', True)

    def get_storage_path(self, camera_id: str) -> str:
        """카메라별 저장 경로 반환"""
        return self.get(f'recording.cameras.{camera_id}.storage_path', f'videos/cam{camera_id}')

# 글로벌 설정 관리자 인스턴스
config_manager = ConfigManager()