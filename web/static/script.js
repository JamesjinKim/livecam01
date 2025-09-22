// SHT CCTV System - Dual View Support JavaScript - 중복 제거 버전

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

    // 녹화 상태 체크 활성화
    updateRecordingStatus();
    recordingStatusInterval = setInterval(updateRecordingStatus, 3000);

    // 스트리밍 상태 인디케이터 초기화
    setTimeout(() => {
        updateRecordingIndicator();
        console.log('[INIT] Streaming indicator initialized');
    }, 100); // DOM이 완전히 로드된 후 실행
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
                    // 720p는 현재 지원하지 않음 - 기본값으로 처리
                    console.warn('[RESOLUTION] 720p is not supported, defaulting to 640x480');
                    document.getElementById('res-640-btn').classList.add('active');
                    document.getElementById('dual-view').className = 'dual-view-container resolution-640';
                    document.getElementById('single-view').className = 'single-view-container resolution-640' +
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
    console.log('[HEARTBEAT] 스트림 상태 체크 시작, 모드:', currentViewMode);

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
                console.log('[DEBUG-HEARTBEAT] 첫번째 인디케이터 텍스트를 LIVE로 변경');
                text.textContent = 'LIVE';
                statusElement.textContent = '스트리밍 중';
                statusElement.style.color = '#27ae60';
                console.log('[HEARTBEAT] LIVE 상태');
                updateRecordingIndicator(); // REC 인디케이터를 REC로 업데이트
            } else if (response.status === 503) {
                indicator.className = 'heartbeat-indicator black';
                console.log('[DEBUG-HEARTBEAT] 첫번째 인디케이터 텍스트를 OFFLINE로 변경');
                text.textContent = 'OFFLINE';
                statusElement.textContent = '오프라인';
                statusElement.style.color = '#6c757d';
                console.log('[HEARTBEAT] OFFLINE 상태');
                updateRecordingIndicator(); // REC 인디케이터를 OFFLINE으로 업데이트
            } else if (response.status === 423) {
                indicator.className = 'heartbeat-indicator yellow';
                console.log('[DEBUG-HEARTBEAT] 첫번째 인디케이터 텍스트를 BUSY로 변경');
                text.textContent = 'BUSY';
                statusElement.textContent = '접속 제한';
                statusElement.style.color = '#ffc107';
                console.log('[HEARTBEAT] BUSY 상태');
                updateRecordingIndicator(); // REC 인디케이터를 IDLE로 업데이트
            } else {
                indicator.className = 'heartbeat-indicator yellow';
                console.log('[DEBUG-HEARTBEAT] 첫번째 인디케이터 텍스트를 DELAY로 변경');
                text.textContent = 'DELAY';
                statusElement.textContent = '지연';
                statusElement.style.color = '#ffc107';
                console.log('[HEARTBEAT] DELAY 상태:', response.status);
                updateRecordingIndicator(); // REC 인디케이터를 IDLE로 업데이트
            }
        })
        .catch(error => {
            console.error('[HEARTBEAT] 오류:', error);

            const indicator = document.getElementById('heartbeat-indicator');
            const text = document.getElementById('heartbeat-text');
            const statusElement = document.getElementById('stream-status');

            if (indicator && text && statusElement) {
                indicator.className = 'heartbeat-indicator black';
                console.log('[DEBUG-HEARTBEAT] 첫번째 인디케이터 텍스트를 OFFLINE로 변경 (catch)');
                text.textContent = 'OFFLINE';
                statusElement.textContent = '서버 연결 끊김';
                statusElement.style.color = '#6c757d';
                updateRecordingIndicator(); // REC 인디케이터를 OFFLINE으로 업데이트
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
        // 녹화 시작 (확인 메시지 없이 직진)
        startRecording(cameraId);
    }
}

// 녹화 시작
function startRecording(cameraId) {
    console.log(`[RECORDING] 카메라 ${cameraId} 녹화 시작 요청`);

    // 버튼 상태 즉시 업데이트
    updateRecordingButton(cameraId, true);

    // 모든 카메라 선택 버튼을 대기 상태로 변경
    disableAllCameraButtons();

    // 스트리밍 상태 즉시 업데이트
    const streamStatusElement = document.getElementById('stream-status');
    if (streamStatusElement) {
        streamStatusElement.textContent = '녹화 준비 중 - 스트리밍 지속 중';
        streamStatusElement.style.color = '#ff6b35';
    }

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

                // 녹화 진행 상태 표시
                if (streamStatusElement) {
                    streamStatusElement.textContent = '녹화 중 - 스트리밍 지속 중';
                    streamStatusElement.style.color = '#e74c3c';
                }

                // 녹화 시작 시 스트리밍 인디케이터는 건드리지 않음
                // updateRecordingIndicator(); // 비활성화: 녹화와 스트리밍 상태 분리

                console.log(`[UI] 카메라 ${cameraId} 녹화 중 UI 업데이트 완료`);
            } else {
                console.error(`[ERROR] 카메라 ${cameraId} 녹화 시작 실패:`, data);
                updateRecordingButton(cameraId, false);
                restoreStreamingStatus();
                alert(`카메라 ${cameraId} 녹화 시작에 실패했습니다.`);
            }
        })
        .catch(error => {
            console.error(`[ERROR] 카메라 ${cameraId} 녹화 시작 실패:`, error);
            updateRecordingButton(cameraId, false);
            restoreStreamingStatus();
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

                // 녹화 중지 시 즉시 카메라 버튼 활성화 및 듀얼 뷰 복원
                checkAndRestoreCameraButtons();
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
            console.log('[RECORDING-STATUS] 녹화 상태 조회:', data);

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

            // REC 상태 인디케이터 업데이트 (전체 시스템 녹화 상태 기반)
            updateRecordingIndicatorBasedOnSystem(data.system_recording);
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

// 두 번째 인디케이터 업데이트 (REC/IDLE/OFFLINE 표시)
function updateRecordingIndicator() {
    console.log('[DEBUG-FUNCTION] updateRecordingIndicator() 함수 호출됨');
    const indicator = document.getElementById('recording-indicator');
    const text = document.getElementById('recording-text');

    if (!indicator || !text) {
        console.log('[DEBUG-FUNCTION] recording-indicator 또는 recording-text 요소를 찾을 수 없음');
        return;
    }

    // 하트비트 상태에 따른 REC/IDLE/OFFLINE 표시
    const heartbeatStatus = document.getElementById('heartbeat-text')?.textContent;

    console.log('[DEBUG-RECORDING] 두번째 인디케이터 업데이트 시작, heartbeatStatus:', heartbeatStatus);

    if (heartbeatStatus === 'LIVE') {
        // 스트리밍 중 = REC 상태
        console.log('[DEBUG-RECORDING] 두번째 인디케이터 텍스트를 REC로 변경');
        indicator.className = 'heartbeat-indicator orange';
        text.textContent = 'REC';
        text.style.color = '#e67e22';
    } else if (heartbeatStatus === 'OFFLINE') {
        // 오프라인 = OFFLINE 상태
        console.log('[DEBUG-RECORDING] 두번째 인디케이터 텍스트를 REC OFF로 변경');
        indicator.className = 'heartbeat-indicator black';
        text.textContent = 'REC';
        text.style.color = '#6c757d';
    } else {
        // 기타 상태 (DELAY, BUSY 등) = IDLE 상태
        console.log('[DEBUG-RECORDING] 두번째 인디케이터 텍스트를 IDLE로 변경');
        indicator.className = 'heartbeat-indicator gray';
        text.textContent = 'IDLE';
        text.style.color = '#95a5a6';
    }

    console.log('[DEBUG-RECORDING] 두번째 인디케이터 최종 텍스트:', text.textContent);
}

// 시스템 녹화 상태 기반 인디케이터 업데이트 (새로운 함수)
function updateRecordingIndicatorBasedOnSystem(isSystemRecording) {
    console.log('[DEBUG-RECORDING] 시스템 녹화 상태 기반 업데이트:', isSystemRecording);

    const indicator = document.getElementById('recording-indicator');
    const text = document.getElementById('recording-text');

    if (!indicator || !text) {
        console.log('[DEBUG-RECORDING] recording-indicator 또는 recording-text 요소를 찾을 수 없음');
        return;
    }

    if (isSystemRecording) {
        // 실제 녹화 중일 때
        indicator.className = 'heartbeat-indicator red';
        text.textContent = 'REC';
        text.style.color = '#e74c3c';
        console.log('[DEBUG-RECORDING] 시스템 녹화 중 - REC 표시');
    } else {
        // 녹화 중이 아닐 때
        indicator.className = 'heartbeat-indicator gray';
        text.textContent = 'IDLE';
        text.style.color = '#95a5a6';
        console.log('[DEBUG-RECORDING] 시스템 대기 중 - IDLE 표시');
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

            // 녹화 완료 후 자동 스트리밍 재개 표시
            setTimeout(() => {
                statusElement.textContent = '대기';
                statusElement.style.color = '';

                // 스트리밍 상태 자동 복원
                restoreStreamingStatus();

                // 카메라 선택 버튼 복원 및 듀얼 뷰로 자동 복원
                restoreToDualView();

                // 하트비트 상태 복원
                const indicator = document.getElementById('heartbeat-indicator');
                const text = document.getElementById('heartbeat-text');
                if (indicator && text) {
                    indicator.className = 'heartbeat-indicator green';
                    text.textContent = 'LIVE';
                }

                console.log(`[UI] 카메라 ${cameraId} 녹화 완료 후 자동 복원 완료`);
            }, 3000);
        } else {
            statusElement.textContent = '대기';
            statusElement.style.color = '';
        }
    }
}

// 스트리밍 상태 복원 함수
function restoreStreamingStatus() {
    const streamStatusElement = document.getElementById('stream-status');
    if (streamStatusElement) {
        streamStatusElement.textContent = '스트리밍 중';
        streamStatusElement.style.color = '#27ae60';
    }
}

// 모든 카메라 선택 버튼 비활성화 (녹화 중)
function disableAllCameraButtons() {
    document.querySelectorAll('.camera-btn').forEach(btn => {
        btn.classList.remove('active', 'active-dual');
        btn.style.opacity = '0.5';
        btn.style.pointerEvents = 'none';
        btn.style.background = '#f8f9fa';
        btn.style.color = '#6c757d';
        btn.style.borderColor = '#dee2e6';
    });
    console.log('[UI] 카메라 선택 버튼들 비활성화됨 (녹화 모드)');
}

// 모든 카메라 선택 버튼 활성화 (녹화 완료 후)
function enableAllCameraButtons() {
    document.querySelectorAll('.camera-btn').forEach(btn => {
        btn.style.opacity = '';
        btn.style.pointerEvents = '';
        btn.style.background = '';
        btn.style.color = '';
        btn.style.borderColor = '';
    });

    // 현재 뷰 모드에 따라 활성 버튼 복원
    if (currentViewMode === 'dual') {
        setActiveButton('dual-btn');
    } else if (currentCamera !== null) {
        setActiveButton(`cam${currentCamera}-btn`);
    }

    console.log('[UI] 카메라 선택 버튼들 활성화됨 (스트리밍 모드)');
}

// 녹화 상태 확인 후 카메라 버튼 복원
function checkAndRestoreCameraButtons() {
    // 모든 카메라가 녹화 중이 아닌지 확인
    const isAnyRecording = recordingStates[0] || recordingStates[1];

    if (!isAnyRecording) {
        console.log('[UI] 모든 녹화 중지됨 - 듀얼 뷰로 자동 복원');
        restoreToDualView();
    }
}

// 듀얼 뷰로 자동 복원
function restoreToDualView() {
    // 카메라 버튼 활성화
    enableAllCameraButtons();

    // 듀얼 뷰로 강제 전환
    currentViewMode = 'dual';
    currentCamera = null;

    // UI 업데이트
    document.getElementById('dual-view').classList.remove('hidden');
    document.getElementById('single-view').classList.add('hidden');
    setActiveButton('dual-btn');

    // 상태 텍스트 업데이트
    const currentCameraElement = document.getElementById('current-camera');
    const viewModeElement = document.getElementById('view-mode');

    if (currentCameraElement) currentCameraElement.textContent = '듀얼';
    if (viewModeElement) viewModeElement.textContent = '듀얼';

    // 듀얼 모드 API 호출
    fetch('/api/dual_mode/true', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('[DUAL] 자동 듀얼 모드 활성화 성공');
                // 스트림 소스 재설정
                setTimeout(() => {
                    document.getElementById('video-stream-0').src = '/stream/0?' + Date.now();
                    document.getElementById('video-stream-1').src = '/stream/1?' + Date.now();
                }, 1000);
            }
        })
        .catch(error => console.error('[ERROR] 자동 듀얼 모드 활성화 실패:', error));

    console.log('[UI] 듀얼 뷰로 자동 복원 완료');
}

// 녹화 토글 함수 (HTML에서 호출)
function toggleRecording(cameraId) {
    console.log(`[RECORDING] 카메라 ${cameraId} 녹화 토글 요청`);

    if (recordingStates[cameraId]) {
        // 녹화 중이면 중지
        stopRecording(cameraId);
    } else {
        // 대기 중이면 시작
        startRecording(cameraId);
    }
}

// 카메라 전환 (레거시 호환성)
function switchCamera(cameraId) {
    switchToSingleView(cameraId);
}

// 녹화 시작 함수
function startRecording(cameraId) {
    console.log(`[RECORDING] 카메라 ${cameraId} 녹화 시작 요청`);

    // 버튼 비활성화 및 로딩 상태
    const button = document.getElementById(`record-cam${cameraId}-btn`);
    if (button) {
        button.textContent = `카메라${cameraId} 녹화 시작 중...`;
        button.disabled = true;
    }

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
                updateRecordingButton(cameraId, true);

                // 로그만 출력 (알림 메시지 제거)
                console.log(`[SUCCESS] 카메라 ${cameraId} 30초 녹화 시작 성공`);
            } else {
                console.error(`[ERROR] 카메라 ${cameraId} 녹화 시작 실패:`, data);
                // 실패 시에만 알림 표시
                alert(`카메라 ${cameraId} 녹화 시작에 실패했습니다.`);
            }
        })
        .catch(error => {
            console.error(`[ERROR] 카메라 ${cameraId} 녹화 시작 실패:`, error);
            alert(`카메라 ${cameraId} 녹화 시작에 실패했습니다: ${error.message}`);
        })
        .finally(() => {
            // 버튼 상태 복원
            if (button) {
                button.disabled = false;
                updateRecordingButton(cameraId, recordingStates[cameraId]);
            }
        });
}

// 녹화 중지 함수
function stopRecording(cameraId) {
    console.log(`[RECORDING] 카메라 ${cameraId} 녹화 중지 요청`);

    fetch(`/api/recording/stop/${cameraId}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log(`[RECORDING] 카메라 ${cameraId} 녹화 중지 성공`);
                recordingStates[cameraId] = false;
                updateRecordingButton(cameraId, false);
                // 중지 알림 제거
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

// 페이지 언로드 시 정리
window.addEventListener('beforeunload', function() {
    if (statsInterval) clearInterval(statsInterval);
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    if (recordingStatusInterval) clearInterval(recordingStatusInterval);
});