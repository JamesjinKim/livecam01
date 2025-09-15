// SHT CCTV System - Dual View Support JavaScript

let currentViewMode = 'dual';  // 'dual', 'single'
let currentCamera = null;  // null (dual), 0, or 1
let currentResolution = '640x480';
let statsInterval = null;
let heartbeatInterval = null;
let recordingStatusInterval = null;
let recordingStates = { 0: false, 1: false };  // 녹화 상태 추적
let previousViewMode = 'dual';  // 녹화 전 뷰 모드 저장
let previousCamera = null;  // 녹화 전 카메라 저장
let isApiCallInProgress = false;  // API 호출 중복 방지

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', function() {
    console.log('[INIT] CCTV 시스템 초기화');
    
    // 듀얼 모드로 시작
    initializeDualMode();
    
    // 통계 업데이트 시작
    updateStats();
    statsInterval = setInterval(updateStats, 2000);
    
    // 하트비트 체크 시작
    checkStreamActivity();
    heartbeatInterval = setInterval(checkStreamActivity, 3000);

    // 녹화 상태 체크 시작
    updateRecordingStatus();
    recordingStatusInterval = setInterval(updateRecordingStatus, 2000);
});

// 듀얼 모드 초기화
function initializeDualMode() {
    console.log('[INIT] 듀얼 모드 초기화 시작');
    
    // 기본적으로 듀얼 뷰 표시
    currentViewMode = 'dual';
    currentCamera = null;
    
    // UI 업데이트
    document.getElementById('dual-view').classList.remove('hidden');
    document.getElementById('single-view').classList.add('hidden');
    setActiveButton('dual-btn');
    
    // 안전한 요소 업데이트
    const currentCameraElement = document.getElementById('current-camera');
    const viewModeElement = document.getElementById('view-mode');
    
    if (currentCameraElement) currentCameraElement.textContent = '듀얼';
    if (viewModeElement) viewModeElement.textContent = '듀얼';
    
    // 듀얼 모드 API 호출
    fetch('/api/dual_mode/true', { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log('[DUAL] 듀얼 모드 API 활성화 성공');
                // 스트림 소스 설정
                document.getElementById('video-stream-0').src = '/stream/0?' + Date.now();
                document.getElementById('video-stream-1').src = '/stream/1?' + Date.now();
            } else {
                console.error('[ERROR] 듀얼 모드 API 실패:', data);
            }
        })
        .catch(error => {
            console.error('[ERROR] 듀얼 모드 초기화 실패:', error);
            // API 실패 시에도 UI는 듀얼 모드로 표시
        });
}

// 듀얼 뷰로 전환
function switchToDualView() {
    console.log('[VIEW] 듀얼 뷰로 전환 클릭');

    // API 호출 중복 방지
    if (isApiCallInProgress) {
        console.log('[VIEW] API 호출 중... 대기');
        return;
    }

    // 즉시 UI 업데이트
    currentViewMode = 'dual';
    currentCamera = null;

    // UI 업데이트
    document.getElementById('dual-view').classList.remove('hidden');
    document.getElementById('single-view').classList.add('hidden');

    // 버튼 활성화 상태 업데이트
    setActiveButton('dual-btn');

    // 상태 텍스트 업데이트 (안전한 접근)
    const currentCameraElement2 = document.getElementById('current-camera');
    const viewModeElement2 = document.getElementById('view-mode');

    if (currentCameraElement2) currentCameraElement2.textContent = '듀얼';
    if (viewModeElement2) viewModeElement2.textContent = '듀얼';

    // 스트림 소스 재설정 (듀얼 모드)
    document.getElementById('video-stream-0').src = '/stream/0?' + Date.now();
    document.getElementById('video-stream-1').src = '/stream/1?' + Date.now();

    // 듀얼 모드 API 호출 (중복 방지)
    isApiCallInProgress = true;
    fetch('/api/dual_mode/true', { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log('[DUAL] 듀얼 모드 활성화 성공');
            } else {
                console.error('[ERROR] 듀얼 모드 API 실패:', data);
            }
        })
        .catch(error => console.error('[ERROR] 듀얼 뷰 전환 실패:', error))
        .finally(() => {
            isApiCallInProgress = false;
        });
}

// 싱글 뷰로 전환
function switchToSingleView(cameraId) {
    console.log(`[VIEW] 싱글 뷰로 전환 클릭 - 카메라 ${cameraId}`);
    
    // 즉시 UI 업데이트
    currentViewMode = 'single';
    currentCamera = cameraId;
    
    // UI 업데이트
    document.getElementById('dual-view').classList.add('hidden');
    document.getElementById('single-view').classList.remove('hidden');
    
    // 버튼 활성화 상태 업데이트
    setActiveButton(`cam${cameraId}-btn`);
    
    // 상태 텍스트 업데이트 (안전한 접근)
    const currentCameraElement3 = document.getElementById('current-camera');
    const viewModeElement3 = document.getElementById('view-mode');
    const singleCameraLabel = document.getElementById('single-camera-label');
    
    if (currentCameraElement3) currentCameraElement3.textContent = cameraId;
    if (viewModeElement3) viewModeElement3.textContent = `카메라 ${cameraId}`;
    if (singleCameraLabel) singleCameraLabel.textContent = `카메라 ${cameraId}`;
    
    // 카메라 전환 API 호출 (스트림 업데이트 전에 먼저 실행)
    fetch(`/switch/${cameraId}`, { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log(`[VIEW] 카메라 ${cameraId}로 전환 성공`);
                // API 성공 후 스트림 소스 업데이트 (지연 적용)
                setTimeout(() => {
                    document.getElementById('video-stream-single').src = '/stream?' + Date.now();
                    console.log(`[STREAM] 카메라 ${cameraId} 스트림 소스 업데이트`);
                }, 500);
            } else {
                console.error(`[ERROR] 카메라 ${cameraId} 전환 API 실패:`, data);
            }
        })
        .catch(error => console.error(`[ERROR] 카메라 ${cameraId} 전환 실패:`, error));
}

// 버튼 활성화 상태 설정
function setActiveButton(buttonId) {
    // 모든 카메라 버튼 비활성화
    document.querySelectorAll('.camera-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.classList.remove('active-dual');
    });
    
    // 선택된 버튼 활성화
    const activeBtn = document.getElementById(buttonId);
    if (activeBtn) {
        if (buttonId === 'dual-btn') {
            activeBtn.classList.add('active-dual');
        } else {
            activeBtn.classList.add('active');
        }
    }
}

// 뷰 모드 업데이트
function updateViewMode(mode) {
    currentViewMode = mode;
    
    if (mode === 'dual') {
        document.getElementById('dual-view').classList.remove('hidden');
        document.getElementById('single-view').classList.add('hidden');
    } else {
        document.getElementById('dual-view').classList.add('hidden');
        document.getElementById('single-view').classList.remove('hidden');
    }
}

// 해상도 변경
function changeResolution(resolution) {
    console.log(`[RESOLUTION] ${resolution}로 변경 요청`);
    
    fetch(`/api/resolution/${resolution}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log(`[OK] 해상도 변경 완료: ${resolution}`);
                currentResolution = resolution;
                
                // 해상도 표시 업데이트
                const [width, height] = resolution.split('x');
                document.getElementById('resolution').textContent = `${width}×${height}`;
                
                // 해상도 버튼 활성화 상태 업데이트
                document.querySelectorAll('.resolution-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                
                if (resolution === '640x480') {
                    document.getElementById('res-640-btn').classList.add('active');
                    document.getElementById('dual-view').className = 'dual-view-container resolution-640';
                    document.getElementById('single-view').className = 'single-view-container resolution-640' + 
                        (currentViewMode === 'dual' ? ' hidden' : '');
                } else {
                    document.getElementById('res-720-btn').classList.add('active');
                    document.getElementById('dual-view').className = 'dual-view-container resolution-1280';
                    document.getElementById('single-view').className = 'single-view-container resolution-1280' + 
                        (currentViewMode === 'dual' ? ' hidden' : '');
                }
                
                // 스트림 재시작
                setTimeout(() => {
                    if (currentViewMode === 'dual') {
                        document.getElementById('video-stream-0').src = '/stream/0?' + Date.now();
                        document.getElementById('video-stream-1').src = '/stream/1?' + Date.now();
                    } else {
                        document.getElementById('video-stream-single').src = '/stream?' + Date.now();
                    }
                }, 1000);
            }
        })
        .catch(error => {
            console.error('[ERROR] 해상도 변경 실패:', error);
            alert('해상도 변경에 실패했습니다.');
        });
}

// 통계 업데이트
function updateStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            // FPS 업데이트
            document.getElementById('fps').textContent = data.stats.fps || '0.0';
            
            // 프레임 수 업데이트
            document.getElementById('frame-count').textContent = data.stats.frame_count || '0';
            
            // 평균 프레임 크기 업데이트
            const avgSize = data.stats.avg_frame_size || 0;
            document.getElementById('frame-size').textContent = `${Math.round(avgSize / 1024)} KB`;
            
            // 클라이언트 수 업데이트
            const activeClients = data.active_clients || 0;
            const maxClients = data.max_clients || 1;
            document.getElementById('client-count').textContent = `${activeClients}/${maxClients}`;
        })
        .catch(error => {
            console.error('[ERROR] 통계 조회 실패:', error);
        });
}

// 스트림 활성 상태 체크
function checkStreamActivity() {
    // 녹화 중이면 하트비트 체크 건너뛰기
    const isAnyRecording = recordingStates[0] || recordingStates[1];
    if (isAnyRecording) {
        console.log('[HEARTBEAT] 녹화 중이므로 상태 체크 건너뛰기');
        return;
    }

    console.log('[HEARTBEAT] 상태 체크 시작, 모드:', currentViewMode);

    // 현재 뷰 모드에 따라 적절한 스트림 체크
    const checkUrl = currentViewMode === 'dual' ? '/stream/0' : '/stream';

    fetch(checkUrl, { method: 'HEAD' })
        .then(response => {
            console.log('[HEARTBEAT] 응답 상태:', response.status);

            const indicator = document.getElementById('heartbeat-indicator');
            const text = document.getElementById('heartbeat-text');
            const statusElement = document.getElementById('stream-status');

            if (!indicator || !text || !statusElement) {
                console.error('[HEARTBEAT] HTML 요소를 찾을 수 없음');
                return;
            }

            if (response.status === 200) {
                indicator.className = 'heartbeat-indicator green';
                text.textContent = 'LIVE';
                statusElement.textContent = '스트리밍 중';
                console.log('[HEARTBEAT] LIVE 상태');
            } else if (response.status === 503) {
                indicator.className = 'heartbeat-indicator red';
                text.textContent = 'OFFLINE';
                statusElement.textContent = '오프라인';
                console.log('[HEARTBEAT] OFFLINE 상태');
            } else if (response.status === 423) {
                indicator.className = 'heartbeat-indicator yellow';
                text.textContent = 'BUSY';
                statusElement.textContent = '접속 제한';
                console.log('[HEARTBEAT] BUSY 상태');
            } else {
                indicator.className = 'heartbeat-indicator yellow';
                text.textContent = 'DELAY';
                statusElement.textContent = '지연';
                console.log('[HEARTBEAT] DELAY 상태:', response.status);
            }
        })
        .catch(error => {
            console.error('[HEARTBEAT] 오류:', error);

            const indicator = document.getElementById('heartbeat-indicator');
            const text = document.getElementById('heartbeat-text');
            const statusElement = document.getElementById('stream-status');

            if (indicator && text && statusElement) {
                indicator.className = 'heartbeat-indicator black';
                text.textContent = 'ERROR';
                statusElement.textContent = '연결 오류';
            }
        });
}

// 녹화 토글 (시작/중지)
function toggleRecording(cameraId) {
    console.log(`[RECORDING] 카메라 ${cameraId} 녹화 토글 클릭`);

    const isRecording = recordingStates[cameraId];

    if (isRecording) {
        // 녹화 중지
        stopRecording(cameraId);
    } else {
        // 녹화 시작 전 확인
        if (currentViewMode === 'dual' || currentCamera !== null) {
            const message = currentViewMode === 'dual'
                ? `카메라${cameraId} 녹화를 시작하면 현재 듀얼 스트리밍이 중단됩니다.\n녹화 완료 후 자동으로 스트리밍이 재개됩니다.\n\n계속하시겠습니까?`
                : `카메라${cameraId} 녹화를 시작하면 현재 카메라${currentCamera} 스트리밍이 중단됩니다.\n녹화 완료 후 자동으로 스트리밍이 재개됩니다.\n\n계속하시겠습니까?`;

            if (!confirm(message)) {
                console.log(`[RECORDING] 카메라 ${cameraId} 녹화 시작 취소됨`);
                return;
            }

            // 현재 뷰 모드 저장
            previousViewMode = currentViewMode;
            previousCamera = currentCamera;
        }

        // 녹화 시작
        startRecording(cameraId);
    }
}

// 녹화 시작
function startRecording(cameraId) {
    console.log(`[RECORDING] 카메라 ${cameraId} 녹화 시작 요청`);

    // 버튼 상태 즉시 업데이트
    updateRecordingButton(cameraId, true);

    fetch(`/api/recording/start/${cameraId}`, { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                if (response.status === 409) {
                    throw new Error('이미 녹화 중입니다');
                } else {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log(`[RECORDING] 카메라 ${cameraId} 녹화 시작 성공`);
                recordingStates[cameraId] = true;

                // 스트리밍 중단 안내 메시지 표시
                if (cameraId === currentCamera || currentViewMode === 'dual') {
                    showRecordingOverlay(cameraId);
                }
            } else {
                console.error(`[ERROR] 카메라 ${cameraId} 녹화 시작 실패:`, data);
                updateRecordingButton(cameraId, false);
                alert(`카메라 ${cameraId} 녹화 시작에 실패했습니다.`);
            }
        })
        .catch(error => {
            console.error(`[ERROR] 카메라 ${cameraId} 녹화 시작 실패:`, error);
            updateRecordingButton(cameraId, false);
            alert(`카메라 ${cameraId} 녹화 시작에 실패했습니다: ${error.message}`);
        });
}

// 녹화 중지
function stopRecording(cameraId) {
    console.log(`[RECORDING] 카메라 ${cameraId} 녹화 중지 요청`);

    fetch(`/api/recording/stop/${cameraId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log(`[RECORDING] 카메라 ${cameraId} 녹화 중지 성공`);
                recordingStates[cameraId] = false;
                updateRecordingButton(cameraId, false);

                // 오버레이 제거
                hideRecordingOverlay(cameraId);
            } else {
                console.error(`[ERROR] 카메라 ${cameraId} 녹화 중지 실패:`, data);
                alert(`카메라 ${cameraId} 녹화 중지에 실패했습니다.`);
            }
        })
        .catch(error => {
            console.error(`[ERROR] 카메라 ${cameraId} 녹화 중지 실패:`, error);
            alert(`카메라 ${cameraId} 녹화 중지에 실패했습니다: ${error.message}`);
        });
}

// 녹화 상태 업데이트
function updateRecordingStatus() {
    fetch('/api/recording/status')
        .then(response => response.json())
        .then(data => {
            // 카메라 0 상태 업데이트
            const cam0Status = data.camera_0;
            if (cam0Status) {
                recordingStates[0] = cam0Status.recording;
                updateRecordingButton(0, cam0Status.recording);
                updateRecordingStatusText(0, cam0Status);
            }

            // 카메라 1 상태 업데이트
            const cam1Status = data.camera_1;
            if (cam1Status) {
                recordingStates[1] = cam1Status.recording;
                updateRecordingButton(1, cam1Status.recording);
                updateRecordingStatusText(1, cam1Status);
            }
        })
        .catch(error => {
            console.error('[ERROR] 녹화 상태 조회 실패:', error);
        });
}

// 녹화 버튼 상태 업데이트
function updateRecordingButton(cameraId, isRecording) {
    const button = document.getElementById(`record-cam${cameraId}-btn`);
    if (!button) return;

    if (isRecording) {
        button.textContent = `카메라${cameraId} 녹화 중지`;
        button.classList.add('recording-active');
        button.classList.remove('recording-idle');
    } else {
        button.textContent = `카메라${cameraId} 녹화(30초)`;
        button.classList.remove('recording-active');
        button.classList.add('recording-idle');
    }
}

// 녹화 상태 텍스트 업데이트
function updateRecordingStatusText(cameraId, status) {
    const statusElement = document.getElementById(`recording-cam${cameraId}`);
    if (!statusElement) return;

    if (status.recording) {
        statusElement.textContent = '녹화 중';
        statusElement.style.color = '#e74c3c';
    } else {
        if (status.status === 'completed') {
            statusElement.textContent = '✅ 완료';
            statusElement.style.color = '#27ae60';
            // 3초 후 대기 상태로 변경
            setTimeout(() => {
                statusElement.textContent = '대기';
                statusElement.style.color = '';
            }, 3000);
        } else {
            statusElement.textContent = '대기';
            statusElement.style.color = '';
        }
    }
}

// 녹화 중 오버레이 표시
function showRecordingOverlay(cameraId) {
    // 구현 예정: 스트림 위에 "녹화 중..." 오버레이 표시
    console.log(`[UI] 카메라 ${cameraId} 녹화 중 오버레이 표시`);
}

// 녹화 오버레이 숨김
function hideRecordingOverlay(cameraId) {
    // 구현 예정: 오버레이 제거
    console.log(`[UI] 카메라 ${cameraId} 녹화 오버레이 숨김`);
}

// 카메라 전환 (레거시 호환성)
function switchCamera(cameraId) {
    switchToSingleView(cameraId);
}

// 녹화 상태 업데이트
function updateRecordingStatus() {
    fetch('/api/recording/status')
        .then(response => response.json())
        .then(data => {
            // 카메라 0 상태 업데이트
            const cam0Status = data.camera_0;
            if (cam0Status) {
                recordingStates[0] = cam0Status.recording;
                updateRecordingButton(0, cam0Status.recording);
                updateRecordingStatusText(0, cam0Status);
            }

            // 카메라 1 상태 업데이트
            const cam1Status = data.camera_1;
            if (cam1Status) {
                recordingStates[1] = cam1Status.recording;
                updateRecordingButton(1, cam1Status.recording);
                updateRecordingStatusText(1, cam1Status);
            }
        })
        .catch(error => {
            console.error('[ERROR] 녹화 상태 조회 실패:', error);
        });
}

// 녹화 버튼 상태 업데이트
function updateRecordingButton(cameraId, isRecording) {
    const button = document.getElementById(`record-cam${cameraId}-btn`);
    if (!button) return;

    if (isRecording) {
        button.textContent = `카메라${cameraId} 녹화 중지`;
        button.classList.add('recording-active');
        button.classList.remove('recording-idle');
    } else {
        button.textContent = `카메라${cameraId} 녹화(30초)`;
        button.classList.remove('recording-active');
        button.classList.add('recording-idle');
    }
}

// 녹화 상태 텍스트 업데이트
function updateRecordingStatusText(cameraId, status) {
    const statusElement = document.getElementById(`recording-cam${cameraId}`);
    const streamStatusElement = document.getElementById('stream-status');
    if (!statusElement) return;

    if (status.recording) {
        statusElement.textContent = '녹화 중';
        statusElement.style.color = '#e74c3c';

        // 스트리밍 상태도 업데이트
        if (streamStatusElement) {
            streamStatusElement.textContent = '녹화 중 - 스트리밍 일시 중단';
            streamStatusElement.style.color = '#ffc107';
        }
    } else {
        if (status.status === 'completed') {
            statusElement.textContent = '✅ 완료';
            statusElement.style.color = '#27ae60';

            // 녹화 완료 후 자동 복원 시작
            setTimeout(() => {
                restorePreviousViewMode();
                statusElement.textContent = '대기';
                statusElement.style.color = '';

                // 스트리밍 상태 복원
                if (streamStatusElement) {
                    streamStatusElement.textContent = '스트리밍 중';
                    streamStatusElement.style.color = '';
                }
            }, 2000);
        } else {
            statusElement.textContent = '대기';
            statusElement.style.color = '';
        }
    }
}

// 이전 뷰 모드 복원 함수
function restorePreviousViewMode() {
    console.log(`[RESTORE] 이전 뷰 모드 복원: ${previousViewMode}, 카메라: ${previousCamera}`);

    if (previousViewMode === 'dual') {
        switchToDualView();
    } else if (previousCamera !== null) {
        switchToSingleView(previousCamera);
    }
}

// 녹화 중 오버레이 표시
function showRecordingOverlay(cameraId) {
    // 구현 예정: 스트림 위에 "녹화 중..." 오버레이 표시
    console.log(`[UI] 카메라 ${cameraId} 녹화 중 오버레이 표시`);
}

// 녹화 오버레이 숨김
function hideRecordingOverlay(cameraId) {
    // 구현 예정: 오버레이 제거
    console.log(`[UI] 카메라 ${cameraId} 녹화 오버레이 숨김`);
}

// 페이지 언로드 시 정리
window.addEventListener('beforeunload', function() {
    if (statsInterval) clearInterval(statsInterval);
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    if (recordingStatusInterval) clearInterval(recordingStatusInterval);
});