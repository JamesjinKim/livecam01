#!/usr/bin/env python3
"""
CCTV 로깅 시스템 모듈
- 날짜별/시간별 로그 파일 자동 생성
- 로그 로테이션 및 아카이브 관리
- 성능 최적화된 비동기 로깅
"""

import logging
import logging.handlers
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import asyncio
import queue
from concurrent.futures import ThreadPoolExecutor


class TimedRotatingFileHandler(logging.handlers.BaseRotatingHandler):
    """시간 기반 로그 파일 로테이션 핸들러"""
    
    def __init__(self, base_filename: str, when: str = 'H', interval: int = 1, 
                 backup_count: int = 168, encoding: str = 'utf-8'):
        """
        Args:
            base_filename: 기본 파일명 (확장자 제외)
            when: 로테이션 단위 ('H'=시간, 'D'=일, 'M'=분)
            interval: 로테이션 간격
            backup_count: 보관할 백업 파일 수 (168 = 7일)
            encoding: 파일 인코딩
        """
        self.base_filename = base_filename
        self.when = when.upper()
        self.interval = interval
        self.backup_count = backup_count
        
        # 현재 로그 파일명 생성
        self.current_filename = self._get_current_filename()
        
        super().__init__(self.current_filename, 'a', encoding=encoding)
        
        # 다음 로테이션 시간 계산
        self.rollover_at = self._compute_rollover()
        
    def _get_current_filename(self) -> str:
        """현재 시간 기반 파일명 생성"""
        now = datetime.now()
        
        if self.when == 'H':  # 시간별
            time_suffix = now.strftime("%Y%m%d%H0000")
        elif self.when == 'D':  # 일별
            time_suffix = now.strftime("%Y%m%d000000")
        elif self.when == 'M':  # 분별 (테스트용)
            time_suffix = now.strftime("%Y%m%d%H%M00")
        else:
            time_suffix = now.strftime("%Y%m%d%H0000")
            
        return f"{self.base_filename}_{time_suffix}.log"
    
    def _compute_rollover(self) -> float:
        """다음 로테이션 시간 계산"""
        now = datetime.now()
        
        if self.when == 'H':
            # 다음 시간의 시작점
            next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return next_hour.timestamp()
        elif self.when == 'D':
            # 다음 날의 시작점
            next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            return next_day.timestamp()
        elif self.when == 'M':
            # 다음 분의 시작점 (테스트용)
            next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            return next_minute.timestamp()
        else:
            return now.timestamp() + 3600  # 기본 1시간
    
    def shouldRollover(self, record) -> bool:
        """로테이션 필요 여부 확인"""
        return time.time() >= self.rollover_at
    
    def doRollover(self):
        """로그 파일 로테이션 수행"""
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # 새 파일명 생성
        new_filename = self._get_current_filename()
        
        # 파일명이 변경된 경우에만 로테이션
        if new_filename != self.current_filename:
            self.current_filename = new_filename
            self.baseFilename = new_filename
            
            # 오래된 파일 정리
            self._cleanup_old_files()
        
        # 새 파일 열기
        if not self.stream:
            self.stream = self._open()
        
        # 다음 로테이션 시간 계산
        self.rollover_at = self._compute_rollover()
    
    def _cleanup_old_files(self):
        """오래된 로그 파일 정리"""
        if self.backup_count <= 0:
            return
            
        log_dir = Path(self.base_filename).parent
        base_name = Path(self.base_filename).name
        
        # 같은 패턴의 로그 파일 검색
        pattern = f"{base_name}_*.log"
        log_files = list(log_dir.glob(pattern))
        
        # 생성 시간 기준 정렬 (오래된 것부터)
        log_files.sort(key=lambda x: x.stat().st_ctime)
        
        # 백업 개수 초과 시 오래된 파일 삭제
        while len(log_files) > self.backup_count:
            old_file = log_files.pop(0)
            try:
                old_file.unlink()
                print(f"🗑️ Removed old log file: {old_file.name}")
            except OSError as e:
                print(f"⚠️ Failed to remove {old_file}: {e}")


class AsyncLogHandler(logging.Handler):
    """비동기 로그 처리 핸들러 (성능 최적화)"""
    
    def __init__(self, target_handler: logging.Handler):
        super().__init__()
        self.target_handler = target_handler
        self.log_queue = queue.Queue(maxsize=1000)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="LogWriter")
        self.shutdown_flag = threading.Event()
        
        # 백그라운드 로그 처리 스레드 시작
        self._start_log_processor()
    
    def emit(self, record):
        """로그 레코드를 큐에 추가"""
        try:
            if not self.shutdown_flag.is_set():
                self.log_queue.put_nowait(record)
        except queue.Full:
            # 큐가 가득 찬 경우 가장 오래된 로그 제거 후 추가
            try:
                self.log_queue.get_nowait()
                self.log_queue.put_nowait(record)
            except queue.Empty:
                pass
    
    def _start_log_processor(self):
        """백그라운드 로그 처리 스레드 시작"""
        def process_logs():
            while not self.shutdown_flag.is_set():
                try:
                    record = self.log_queue.get(timeout=1.0)
                    self.target_handler.emit(record)
                    self.log_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"⚠️ Log processing error: {e}")
        
        self.executor.submit(process_logs)
    
    def close(self):
        """핸들러 종료"""
        self.shutdown_flag.set()
        
        # 남은 로그 처리
        while not self.log_queue.empty():
            try:
                record = self.log_queue.get_nowait()
                self.target_handler.emit(record)
            except queue.Empty:
                break
        
        self.executor.shutdown(wait=True)
        self.target_handler.close()
        super().close()


class CCTVLogger:
    """CCTV 시스템 전용 로거"""
    
    def __init__(self, 
                 log_dir: str = "logs",
                 log_level: str = "INFO",
                 console_output: bool = True,
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 168,  # 7일 (시간별)
                 async_logging: bool = True):
        """
        Args:
            log_dir: 로그 디렉토리
            log_level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            console_output: 콘솔 출력 여부
            max_file_size: 파일당 최대 크기
            backup_count: 보관할 백업 파일 수
            async_logging: 비동기 로깅 사용 여부
        """
        self.log_dir = Path(log_dir)
        self.log_level = getattr(logging, log_level.upper())
        self.console_output = console_output
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.async_logging = async_logging
        
        # 로그 디렉토리 생성
        self.log_dir.mkdir(exist_ok=True)
        (self.log_dir / "archived").mkdir(exist_ok=True)
        
        # 로거 설정
        self.logger = logging.getLogger("CCTV")
        self.logger.setLevel(self.log_level)
        
        # 기존 핸들러 제거
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """로그 핸들러 설정"""
        # 로그 포맷 설정
        detailed_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # 1. 파일 핸들러 (시간별 로테이션)
        base_filename = str(self.log_dir / "cctv")
        file_handler = TimedRotatingFileHandler(
            base_filename=base_filename,
            when='H',  # 시간별 로테이션
            interval=1,
            backup_count=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(detailed_formatter)
        
        # 비동기 로깅 적용
        if self.async_logging:
            file_handler = AsyncLogHandler(file_handler)
        
        self.logger.addHandler(file_handler)
        
        # 2. 콘솔 핸들러
        if self.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # 3. 에러 전용 핸들러 (별도 파일)
        error_filename = str(self.log_dir / "cctv_error")
        error_handler = TimedRotatingFileHandler(
            base_filename=error_filename,
            when='D',  # 일별 로테이션
            interval=1,
            backup_count=30,  # 30일
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        if self.async_logging:
            error_handler = AsyncLogHandler(error_handler)
        
        self.logger.addHandler(error_handler)
    
    def get_logger(self) -> logging.Logger:
        """로거 인스턴스 반환"""
        return self.logger
    
    def log_system_info(self):
        """시스템 정보 로깅"""
        import platform
        import os
        
        self.logger.info("="*50)
        self.logger.info("CCTV 시스템 시작")
        self.logger.info("="*50)
        self.logger.info(f"플랫폼: {platform.platform()}")
        self.logger.info(f"Python 버전: {platform.python_version()}")
        
        # psutil 대신 기본 모듈 사용
        try:
            cpu_count = os.cpu_count()
            self.logger.info(f"CPU 코어: {cpu_count}")
        except:
            self.logger.info("CPU 코어: 정보 없음")
        
        # 라즈베리파이 메모리 정보 (간단 방식)
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
                for line in meminfo.split('\n'):
                    if 'MemTotal' in line:
                        mem_kb = int(line.split()[1])
                        mem_gb = mem_kb // (1024 * 1024)
                        self.logger.info(f"메모리: {mem_gb}GB")
                        break
        except:
            self.logger.info("메모리: 정보 없음")
        
        self.logger.info(f"로그 레벨: {logging.getLevelName(self.log_level)}")
        self.logger.info(f"로그 디렉토리: {self.log_dir.absolute()}")
        self.logger.info(f"비동기 로깅: {'ON' if self.async_logging else 'OFF'}")
        self.logger.info("="*50)
    
    def cleanup(self):
        """로거 정리"""
        self.logger.info("로깅 시스템 종료 중...")
        
        for handler in self.logger.handlers[:]:
            if isinstance(handler, AsyncLogHandler):
                handler.close()
            self.logger.removeHandler(handler)


# 전역 로거 인스턴스
_cctv_logger: Optional[CCTVLogger] = None


def setup_logger(log_dir: str = "logs", 
                log_level: str = "INFO",
                console_output: bool = True,
                async_logging: bool = True) -> logging.Logger:
    """CCTV 로거 초기화 및 설정"""
    global _cctv_logger
    
    if _cctv_logger is None:
        _cctv_logger = CCTVLogger(
            log_dir=log_dir,
            log_level=log_level,
            console_output=console_output,
            async_logging=async_logging
        )
        _cctv_logger.log_system_info()
    
    return _cctv_logger.get_logger()


def get_logger() -> logging.Logger:
    """기존 로거 인스턴스 반환"""
    global _cctv_logger
    
    if _cctv_logger is None:
        return setup_logger()
    
    return _cctv_logger.get_logger()


def cleanup_logger():
    """로거 정리 및 종료"""
    global _cctv_logger
    
    if _cctv_logger is not None:
        _cctv_logger.cleanup()
        _cctv_logger = None


# 편의 함수들
def log_debug(message: str, **kwargs):
    """디버그 로그"""
    get_logger().debug(message, **kwargs)


def log_info(message: str, **kwargs):
    """정보 로그"""
    get_logger().info(message, **kwargs)


def log_warning(message: str, **kwargs):
    """경고 로그"""
    get_logger().warning(message, **kwargs)


def log_error(message: str, **kwargs):
    """에러 로그"""
    get_logger().error(message, **kwargs)


def log_critical(message: str, **kwargs):
    """치명적 에러 로그"""
    get_logger().critical(message, **kwargs)


# 성능 측정 데코레이터
def log_execution_time(func_name: str = None):
    """함수 실행 시간 로깅 데코레이터"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            name = func_name or func.__name__
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                log_debug(f"⏱️ {name} 실행 시간: {execution_time:.3f}초")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                log_error(f"❌ {name} 실행 실패 ({execution_time:.3f}초): {e}")
                raise
        
        return wrapper
    return decorator


if __name__ == "__main__":
    # 테스트 코드
    logger = setup_logger(log_level="DEBUG", console_output=True)
    
    logger.info("🎬 CCTV 로깅 시스템 테스트 시작")
    logger.debug("디버그 메시지 테스트")
    logger.warning("경고 메시지 테스트")
    logger.error("에러 메시지 테스트")
    
    # 성능 테스트
    @log_execution_time("테스트_함수")
    def test_function():
        time.sleep(0.1)
        return "완료"
    
    result = test_function()
    logger.info(f"함수 결과: {result}")
    
    cleanup_logger()
    print("로깅 시스템 테스트 완료")