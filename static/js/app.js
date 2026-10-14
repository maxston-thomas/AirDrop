/**
 * AirDrop — Offline File Transfer Client Logic
 * Apple macOS/iOS inspired system utility experience.
 * Authoritative connection states, live radar, real-time WebSocket presence,
 * peer-to-peer visual transfer beam animations on BOTH sender and receiver,
 * streaming uploads with accurate speed calculation, SHA-256 cryptographic verification,
 * segmented history filtering, and non-blocking toast notifications.
 */

(function () {
  'use strict';

  // Application State
  const state = {
    role: 'guest', // 'host', 'client', 'guest'
    connectionState: 'WAITING_FOR_DEVICE', // WAITING_FOR_DEVICE, PAIRING_PENDING, CONNECTED, DISCONNECTED
    token: localStorage.getItem('airlink_token') || null,
    hostToken: null,
    pairingCode: '------',
    codeRemaining: 0,
    timerInterval: null,
    durationInterval: null,
    connectedSince: null,
    pendingRequestId: null,
    networkInfo: null,
    ws: null,
    wsConnected: false,
    stagedFiles: [],
    selectedFilesToSend: [],
    activeTransfers: {},
    localInitiatedTransfers: new Set(),
    historyItems: [],
    historyFilter: 'all',
    historySearchQuery: '',
    connectedDevices: []
  };

  // DOM Elements Cache
  const elements = {
    connectionStatusPill: document.getElementById('connectionStatusPill'),
    statusDot: document.getElementById('statusDot'),
    connectionStateLabel: document.getElementById('connectionStateLabel'),
    themeToggleBtn: document.getElementById('themeToggleBtn'),
    helpBtn: document.getElementById('helpBtn'),
    disconnectBtn: document.getElementById('disconnectBtn'),

    // Host & Connection Cards
    hostConnectionCard: document.getElementById('hostConnectionCard'),
    connectionCardHeading: document.getElementById('connectionCardHeading'),
    connectionCardDesc: document.getElementById('connectionCardDesc'),
    waitingForDeviceView: document.getElementById('waitingForDeviceView'),
    connectedDeviceView: document.getElementById('connectedDeviceView'),
    connectedDeviceName: document.getElementById('connectedDeviceName'),
    connectedDeviceIp: document.getElementById('connectedDeviceIp'),
    connectedDeviceDuration: document.getElementById('connectedDeviceDuration'),
    disconnectDeviceBtn: document.getElementById('disconnectDeviceBtn'),

    // QR & Network
    qrContainer: document.getElementById('qrContainer'),
    accessUrlText: document.getElementById('accessUrlText'),
    copyUrlBtn: document.getElementById('copyUrlBtn'),
    refreshNetworkBtn: document.getElementById('refreshNetworkBtn'),
    interfaceSelectorContainer: document.getElementById('interfaceSelectorContainer'),
    interfaceSelect: document.getElementById('interfaceSelect'),
    pairingCodeDisplay: document.getElementById('pairingCodeDisplay'),
    pairingTimerDisplay: document.getElementById('pairingTimerDisplay'),
    refreshCodeLink: document.getElementById('refreshCodeLink'),
    pairingBannerContainer: document.getElementById('pairingBannerContainer'),

    // Client Pairing Form
    clientPairingCard: document.getElementById('clientPairingCard'),
    pairForm: document.getElementById('pairForm'),
    pairCodeInput: document.getElementById('pairCodeInput'),
    submitPairBtn: document.getElementById('submitPairBtn'),
    pairStatusMessage: document.getElementById('pairStatusMessage'),

    // Workspace & Send Files
    sendFilesCard: document.getElementById('sendFilesCard'),
    sendCardHeading: document.getElementById('sendCardHeading'),
    fileCountBadge: document.getElementById('fileCountBadge'),
    dropzone: document.getElementById('dropzone'),
    fileInput: document.getElementById('fileInput'),
    stagedListContainer: document.getElementById('stagedListContainer'),
    stagedCountHeading: document.getElementById('stagedCountHeading'),
    stagedFileList: document.getElementById('stagedFileList'),
    clearSelectionBtn: document.getElementById('clearSelectionBtn'),
    confirmSendBtn: document.getElementById('confirmSendBtn'),

    // Incoming Files / Downloads
    incomingFilesCard: document.getElementById('incomingFilesCard'),
    incomingFilesList: document.getElementById('incomingFilesList'),
    refreshFilesBtn: document.getElementById('refreshFilesBtn'),

    // Active Transfers
    activeTransfersCard: document.getElementById('activeTransfersCard'),
    activeTransferContainer: document.getElementById('activeTransferContainer'),

    // History & Filters
    historyCard: document.getElementById('historyCard'),
    historyList: document.getElementById('historyList'),
    historySearchInput: document.getElementById('historySearchInput'),
    clearHistoryBtn: document.getElementById('clearHistoryBtn'),

    // Modals & Toasts
    checksumModal: document.getElementById('checksumModal'),
    modalFileTitle: document.getElementById('modalFileTitle'),
    modalHashContent: document.getElementById('modalHashContent'),
    copyHashBtn: document.getElementById('copyHashBtn'),
    closeChecksumModal: document.getElementById('closeChecksumModal'),
    dismissChecksumModal: document.getElementById('dismissChecksumModal'),

    helpModal: document.getElementById('helpModal'),
    closeHelpModal: document.getElementById('closeHelpModal'),
    dismissHelpModal: document.getElementById('dismissHelpModal'),
    toastContainer: document.getElementById('toastContainer')
  };

  // --- Utility Functions ---

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    if (!bytes || isNaN(bytes)) return '--';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function formatSpeed(bytesPerSec) {
    if (!bytesPerSec || bytesPerSec <= 0) return '0 KB/s';
    if (bytesPerSec < 1024) return Math.round(bytesPerSec) + ' B/s';
    if (bytesPerSec < 1024 * 1024) return (bytesPerSec / 1024).toFixed(1) + ' KB/s';
    return (bytesPerSec / (1024 * 1024)).toFixed(2) + ' MB/s';
  }

  function formatSeconds(secs) {
    if (!secs || secs <= 0) return '0s';
    if (secs < 60) return Math.round(secs) + 's';
    const m = Math.floor(secs / 60);
    const s = Math.round(secs % 60);
    return `${m}m ${s}s`;
  }

  function formatDuration(startTime) {
    if (!startTime) return 'Connected';
    const elapsedSecs = Math.floor((Date.now() - startTime) / 1000);
    if (elapsedSecs < 60) return `Connected for ${elapsedSecs}s`;
    const m = Math.floor(elapsedSecs / 60);
    const s = elapsedSecs % 60;
    return `Connected for ${m}m ${s}s`;
  }

  function getAuthHeaders() {
    const headers = {};
    const token = state.token || state.hostToken;
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
      headers['X-AirLink-Token'] = token;
    }
    return headers;
  }

  function getDeviceIconSvg(deviceName) {
    const name = (deviceName || '').toLowerCase();
    if (name.includes('iphone') || name.includes('phone') || name.includes('mobile') || name.includes('android') || name.includes('pixel') || name.includes('samsung')) {
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`;
    }
    if (name.includes('ipad') || name.includes('tablet')) {
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`;
    }
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;
  }

  function getFileIconSvg(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'svg', 'bmp'].includes(ext)) {
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`;
    }
    if (['mp4', 'mov', 'mkv', 'webm', 'avi'].includes(ext)) {
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/></svg>`;
    }
    if (['pdf', 'doc', 'docx', 'txt', 'rtf', 'pages'].includes(ext)) {
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`;
    }
    if (['zip', 'tar', 'gz', 'rar', '7z'].includes(ext)) {
      return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`;
    }
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  }

  // --- Toast Notifications ---

  function showToast(message, type = 'info') {
    if (!elements.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
      <div class="toast-indicator" style="background-color: ${type === 'error' ? 'var(--danger)' : type === 'success' ? 'var(--success)' : 'var(--accent)'};"></div>
      <div class="toast-message">${message}</div>
    `;
    elements.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }

  // --- Theme Handling ---

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('airlink_theme', theme);
  }

  function initTheme() {
    const saved = localStorage.getItem('airlink_theme');
    if (saved) {
      applyTheme(saved);
    } else {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(prefersDark ? 'dark' : 'light');
    }
    elements.themeToggleBtn.addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme');
      applyTheme(cur === 'dark' ? 'light' : 'dark');
    });
  }

  // --- Network Info & QR Code ---

  async function loadNetworkInfo() {
    try {
      const res = await fetch('/api/network/info');
      if (!res.ok) return;
      const data = await res.json();
      state.networkInfo = data;

      if (elements.accessUrlText) {
        elements.accessUrlText.textContent = data.access_url;
      }

      // Render QR Code SVG
      if (elements.qrContainer) {
        if (data.qr_code_svg) {
          elements.qrContainer.innerHTML = data.qr_code_svg;
        } else if (data.qr_code_png) {
          elements.qrContainer.innerHTML = `<img src="${data.qr_code_png}" alt="AirDrop QR Code" width="180" height="180">`;
        }
      }

      // Populate Interface Selector if multiple interfaces exist
      if (data.interfaces && data.interfaces.length > 1 && elements.interfaceSelectorContainer) {
        elements.interfaceSelectorContainer.style.display = 'block';
        elements.interfaceSelect.innerHTML = '';
        data.interfaces.forEach(iface => {
          const opt = document.createElement('option');
          opt.value = iface.ip;
          opt.textContent = `${iface.name} (${iface.ip})`;
          if (iface.ip === data.primary_ip) opt.selected = true;
          elements.interfaceSelect.appendChild(opt);
        });

        elements.interfaceSelect.onchange = () => {
          const selectedIp = elements.interfaceSelect.value;
          const newUrl = `http://${selectedIp}:${data.port}`;
          if (elements.accessUrlText) elements.accessUrlText.textContent = newUrl;
        };
      }
    } catch (err) {
      console.warn('Network info load failed:', err);
    }
  }

  // --- Connection State & Role Management ---

  async function checkSessionState() {
    try {
      const res = await fetch('/api/session/state', {
        headers: getAuthHeaders()
      });
      if (!res.ok) return;
      const data = await res.json();
      state.role = data.role;
      state.connectedDevices = data.connected_devices || [];

      if (data.role === 'host') {
        state.hostToken = data.host_token;
        state.token = data.host_token;
        localStorage.setItem('airlink_token', data.host_token);
        updateHostView(data);
      } else if (data.role === 'client' && data.authenticated) {
        updateClientAuthenticatedView();
      } else {
        updateGuestView();
      }

      loadHistory();
      if (data.role === 'client' || data.role === 'host') {
        loadStagedFiles();
      }
    } catch (err) {
      console.error('Session state error:', err);
    }
  }

  function updateHostView(data) {
    elements.hostConnectionCard.style.display = 'block';
    elements.clientPairingCard.style.display = 'none';
    elements.incomingFilesCard.style.display = 'none'; // Laptop stages files, mobile downloads them
    elements.sendCardHeading.textContent = 'Stage Files for Mobile Phone';
    elements.disconnectBtn.style.display = 'inline-flex';

    if (data.pairing_code) {
      state.pairingCode = data.pairing_code;
      state.codeRemaining = data.code_remaining_seconds;
      if (elements.pairingCodeDisplay) elements.pairingCodeDisplay.textContent = data.pairing_code;
      startCodeCountdown();
    }

    // Check authoritative connection state:
    const isDeviceConnected = Boolean(data.is_device_connected && data.connected_devices && data.connected_devices.length > 0);

    if (isDeviceConnected) {
      const device = data.connected_devices[0];
      setConnectionState('CONNECTED', device);
    } else if (data.pending_requests && data.pending_requests.length > 0) {
      setConnectionState('PAIRING_PENDING');
      renderPendingPairingRequests(data.pending_requests);
    } else {
      setConnectionState('WAITING_FOR_DEVICE');
      if (elements.pairingBannerContainer) elements.pairingBannerContainer.innerHTML = '';
    }
  }

  function setConnectionState(newState, deviceData = null) {
    state.connectionState = newState;

    if (newState === 'CONNECTED') {
      elements.statusDot.className = 'status-dot online';
      const devName = deviceData?.device_info?.device_name || deviceData?.device_name || 'Mobile Phone';
      elements.connectionStateLabel.textContent = `Connected: ${devName}`;

      if (elements.waitingForDeviceView) elements.waitingForDeviceView.style.display = 'none';
      if (elements.connectedDeviceView) elements.connectedDeviceView.style.display = 'block';

      if (elements.connectionCardHeading) elements.connectionCardHeading.textContent = 'Connected';
      if (elements.connectionCardDesc) elements.connectionCardDesc.textContent = 'Your device is ready to send and receive files.';

      if (elements.connectedDeviceName) elements.connectedDeviceName.textContent = devName;
      if (elements.connectedDeviceIp) elements.connectedDeviceIp.textContent = deviceData?.client_ip || 'Local Wi-Fi';

      if (!state.connectedSince) state.connectedSince = Date.now();
      startDurationTimer();

    } else if (newState === 'PAIRING_PENDING') {
      elements.statusDot.className = 'status-dot';
      elements.statusDot.style.backgroundColor = 'var(--accent)';
      elements.connectionStateLabel.textContent = 'Device wants to connect';

    } else if (newState === 'WAITING_FOR_DEVICE') {
      elements.statusDot.className = 'status-dot waiting';
      elements.statusDot.style.backgroundColor = '';
      elements.connectionStateLabel.textContent = 'Waiting for device';

      if (elements.waitingForDeviceView) elements.waitingForDeviceView.style.display = 'block';
      if (elements.connectedDeviceView) elements.connectedDeviceView.style.display = 'none';

      if (elements.connectionCardHeading) elements.connectionCardHeading.textContent = 'Ready to share';
      if (elements.connectionCardDesc) elements.connectionCardDesc.textContent = 'Connect a mobile phone or laptop over your local Wi-Fi network to start transferring files.';

      stopDurationTimer();
      state.connectedSince = null;

    } else if (newState === 'DISCONNECTED') {
      elements.statusDot.className = 'status-dot offline';
      elements.connectionStateLabel.textContent = 'Device disconnected';
      setConnectionState('WAITING_FOR_DEVICE');
    }
  }

  function startDurationTimer() {
    stopDurationTimer();
    updateDurationText();
    state.durationInterval = setInterval(updateDurationText, 1000);
  }

  function stopDurationTimer() {
    if (state.durationInterval) {
      clearInterval(state.durationInterval);
      state.durationInterval = null;
    }
  }

  function updateDurationText() {
    if (elements.connectedDeviceDuration && state.connectedSince) {
      elements.connectedDeviceDuration.textContent = formatDuration(state.connectedSince);
    }
  }

  function updateClientAuthenticatedView() {
    elements.connectionStateLabel.textContent = 'Connected to Laptop';
    elements.statusDot.className = 'status-dot online';
    elements.hostConnectionCard.style.display = 'none';
    elements.clientPairingCard.style.display = 'none';
    elements.incomingFilesCard.style.display = 'block';
    elements.sendCardHeading.textContent = 'Upload Files to Laptop';
    elements.disconnectBtn.style.display = 'inline-flex';
  }

  function updateGuestView() {
    elements.connectionStateLabel.textContent = 'Unpaired Mobile Device';
    elements.statusDot.className = 'status-dot offline';
    elements.hostConnectionCard.style.display = 'none';
    elements.clientPairingCard.style.display = 'block';
    elements.incomingFilesCard.style.display = 'none';
    elements.disconnectBtn.style.display = 'none';
  }

  function startCodeCountdown() {
    clearInterval(state.timerInterval);
    if (elements.pairingTimerDisplay) elements.pairingTimerDisplay.textContent = state.codeRemaining;

    state.timerInterval = setInterval(() => {
      state.codeRemaining--;
      if (state.codeRemaining <= 0) {
        clearInterval(state.timerInterval);
        refreshPairingCode();
      } else {
        if (elements.pairingTimerDisplay) elements.pairingTimerDisplay.textContent = state.codeRemaining;
      }
    }, 1000);
  }

  async function refreshPairingCode() {
    try {
      const res = await fetch('/api/pair/new-code', {
        method: 'POST',
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        state.pairingCode = data.pairing_code;
        state.codeRemaining = data.remaining_seconds;
        if (elements.pairingCodeDisplay) elements.pairingCodeDisplay.textContent = data.pairing_code;
        startCodeCountdown();
      }
    } catch (err) {
      console.warn('Failed to refresh pairing code:', err);
    }
  }

  // --- Pairing Banner Rendering ---

  function renderPendingPairingRequests(requests) {
    if (!elements.pairingBannerContainer) return;
    elements.pairingBannerContainer.innerHTML = '';
    requests.forEach(req => {
      const banner = document.createElement('div');
      banner.className = 'pairing-request-alert';
      banner.setAttribute('data-id', req.request_id);
      banner.innerHTML = `
        <div class="pairing-request-header">
          Device Authorization Request: ${req.user_agent.split(' ')[0]} (${req.client_ip})
        </div>
        <div style="font-size: 0.8125rem; color: var(--text-secondary); line-height: 1.4;">
          A mobile device entered pairing code <strong style="font-family: var(--font-mono); font-weight: 700;">${req.code || '******'}</strong> and is requesting permission to transfer files.
        </div>
        <div class="pairing-request-actions">
          <button class="btn btn-secondary btn-sm reject-btn" data-id="${req.request_id}">Reject</button>
          <button class="btn btn-primary btn-sm approve-btn" data-id="${req.request_id}">Approve Device</button>
        </div>
      `;
      elements.pairingBannerContainer.appendChild(banner);

      banner.querySelector('.approve-btn').addEventListener('click', () => handlePairDecision(req.request_id, true));
      banner.querySelector('.reject-btn').addEventListener('click', () => handlePairDecision(req.request_id, false));
    });
  }

  async function handlePairDecision(requestId, isApproved) {
    const banner = document.querySelector(`[data-id="${requestId}"]`);
    if (banner) banner.remove();

    const endpoint = isApproved ? '/api/pair/approve' : '/api/pair/reject';
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify({ request_id: requestId })
      });
      if (res.ok) {
        showToast(isApproved ? 'Device pairing approved' : 'Device pairing rejected');
        checkSessionState();
      }
    } catch (err) {
      console.error('Pairing decision failed:', err);
    }
  }

  // --- Client Pairing Form Handling ---

  if (elements.pairForm) {
    elements.pairForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const code = elements.pairCodeInput.value.trim();
      if (!code || code.length !== 6) {
        elements.pairStatusMessage.textContent = 'Please enter a valid 6-digit code.';
        elements.pairStatusMessage.style.color = 'var(--danger)';
        return;
      }

      elements.submitPairBtn.disabled = true;
      elements.pairStatusMessage.textContent = 'Connecting to laptop...';
      elements.pairStatusMessage.style.color = 'var(--text-muted)';

      try {
        const res = await fetch('/api/pair/request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: code })
        });

        const data = await res.json();
        if (!res.ok) {
          elements.pairStatusMessage.textContent = data.detail || 'Pairing failed';
          elements.pairStatusMessage.style.color = 'var(--danger)';
          elements.submitPairBtn.disabled = false;
          return;
        }

        state.pendingRequestId = data.request_id;
        elements.pairStatusMessage.textContent = 'Code accepted! Please approve pairing on your laptop screen.';
        elements.pairStatusMessage.style.color = 'var(--accent)';

        // Poll for laptop approval
        pollPairingApproval(data.request_id);
      } catch (err) {
        elements.pairStatusMessage.textContent = 'Network error: Unable to reach laptop.';
        elements.pairStatusMessage.style.color = 'var(--danger)';
        elements.submitPairBtn.disabled = false;
      }
    });
  }

  function pollPairingApproval(requestId) {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      if (attempts > 60) {
        clearInterval(interval);
        elements.pairStatusMessage.textContent = 'Pairing request timed out.';
        elements.pairStatusMessage.style.color = 'var(--danger)';
        elements.submitPairBtn.disabled = false;
        return;
      }

      try {
        const res = await fetch(`/api/pair/status/${requestId}`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.status === 'approved' && data.token) {
          clearInterval(interval);
          state.token = data.token;
          localStorage.setItem('airlink_token', data.token);
          elements.pairStatusMessage.textContent = 'Authorized! Connecting...';
          elements.pairStatusMessage.style.color = 'var(--success)';
          showToast('Device authorized successfully!', 'success');
          initWebSocket();
          checkSessionState();
        } else if (data.status === 'rejected') {
          clearInterval(interval);
          elements.pairStatusMessage.textContent = 'Pairing was rejected by the laptop.';
          elements.pairStatusMessage.style.color = 'var(--danger)';
          elements.submitPairBtn.disabled = false;
        } else if (data.status === 'expired') {
          clearInterval(interval);
          elements.pairStatusMessage.textContent = 'Pairing code expired. Please re-enter.';
          elements.pairStatusMessage.style.color = 'var(--danger)';
          elements.submitPairBtn.disabled = false;
        }
      } catch (err) {
        // Retry silently
      }
    }, 600);
  }

  // --- Disconnect Buttons ---

  function handleDisconnect() {
    if (!confirm('Disconnect this AirDrop session?')) return;
    try {
      fetch('/api/session/disconnect', {
        method: 'POST',
        headers: getAuthHeaders()
      });
    } catch (e) {}
    localStorage.removeItem('airlink_token');
    state.token = null;
    state.role = 'guest';
    location.reload();
  }

  if (elements.disconnectBtn) elements.disconnectBtn.addEventListener('click', handleDisconnect);
  if (elements.disconnectDeviceBtn) elements.disconnectDeviceBtn.addEventListener('click', handleDisconnect);

  // --- Drag and Drop / File Input Handling ---

  if (elements.dropzone && elements.fileInput) {
    elements.dropzone.addEventListener('click', () => elements.fileInput.click());

    ['dragenter', 'dragover'].forEach(name => {
      elements.dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        elements.dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(name => {
      elements.dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        elements.dropzone.classList.remove('dragover');
      });
    });

    elements.dropzone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        handleFilesSelected(Array.from(files));
      }
    });

    elements.fileInput.addEventListener('change', () => {
      if (elements.fileInput.files.length > 0) {
        handleFilesSelected(Array.from(elements.fileInput.files));
        elements.fileInput.value = '';
      }
    });
  }

  function handleFilesSelected(files) {
    if (state.role === 'client') {
      // Mobile direct streaming upload to laptop
      files.forEach(file => uploadFileWithProgress(file, 'phone_to_laptop'));
    } else {
      // Laptop: Stage files to be transferred to phone
      state.selectedFilesToSend = [...state.selectedFilesToSend, ...files];
      renderStagedPreview(state.selectedFilesToSend);
    }
  }

  function renderStagedPreview(files) {
    if (!files || files.length === 0) {
      if (elements.stagedListContainer) elements.stagedListContainer.style.display = 'none';
      if (elements.fileCountBadge) elements.fileCountBadge.textContent = 'Ready';
      return;
    }

    if (elements.stagedListContainer) elements.stagedListContainer.style.display = 'block';
    if (elements.fileCountBadge) elements.fileCountBadge.textContent = `${files.length} selected`;
    if (elements.stagedCountHeading) elements.stagedCountHeading.textContent = `${files.length} file${files.length > 1 ? 's' : ''} ready to transfer`;
    if (elements.stagedFileList) elements.stagedFileList.innerHTML = '';

    files.forEach((file, index) => {
      const li = document.createElement('li');
      li.className = 'file-preview-item';
      li.innerHTML = `
        <div class="file-icon-box">
          ${getFileIconSvg(file.name)}
        </div>
        <div class="file-info-col">
          <div class="file-title-text">${file.name}</div>
          <div class="file-meta-subtext">${formatBytes(file.size)} &bull; Lossless binary</div>
        </div>
        <div>
          <button class="btn btn-secondary btn-icon btn-sm remove-file-btn" data-index="${index}" title="Remove file">&times;</button>
        </div>
      `;
      elements.stagedFileList.appendChild(li);

      li.querySelector('.remove-file-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        state.selectedFilesToSend.splice(index, 1);
        renderStagedPreview(state.selectedFilesToSend);
      });
    });
  }

  if (elements.clearSelectionBtn) {
    elements.clearSelectionBtn.addEventListener('click', () => {
      state.selectedFilesToSend = [];
      renderStagedPreview([]);
    });
  }

  if (elements.confirmSendBtn) {
    elements.confirmSendBtn.addEventListener('click', async () => {
      if (state.selectedFilesToSend.length === 0) return;

      elements.confirmSendBtn.disabled = true;
      elements.confirmSendBtn.textContent = 'Preparing...';

      const formData = new FormData();
      state.selectedFilesToSend.forEach(f => formData.append('files', f));

      try {
        const res = await fetch('/api/stage-files', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: formData
        });
        if (res.ok) {
          showToast(`Staged ${state.selectedFilesToSend.length} file(s) for mobile download`, 'success');
          state.selectedFilesToSend = [];
          renderStagedPreview([]);
          loadStagedFiles();
          loadHistory();
        } else {
          const err = await res.json();
          alert('Staging failed: ' + (err.detail || 'Unknown error'));
        }
      } catch (e) {
        showToast('Network error while staging files', 'error');
      } finally {
        elements.confirmSendBtn.disabled = false;
        elements.confirmSendBtn.textContent = 'Transfer Now';
      }
    });
  }

  // --- Apple AirDrop P2P Transfer Beam & Progress Rendering ---

  function renderTransferCard(transferId, meta) {
    if (elements.activeTransfersCard) elements.activeTransfersCard.style.display = 'block';

    let card = document.getElementById(`card_${transferId}`);
    if (!card) {
      card = document.createElement('div');
      card.className = `transfer-card ${meta.isOutgoing ? 'outgoing-transfer' : 'incoming-transfer'}`;
      card.id = `card_${transferId}`;
      elements.activeTransferContainer.prepend(card);
    }

    const dirBadgeClass = meta.isOutgoing ? 'dir-badge-outgoing' : 'dir-badge-incoming';
    const dirLabel = meta.isOutgoing ? 'Outgoing Transfer' : 'Incoming Transfer';
    const isReverse = !meta.isOutgoing;
    if (isReverse) card.classList.add('direction-reverse');

    card.innerHTML = `
      <div class="transfer-card-header">
        <div class="transfer-card-title-group">
          <div class="file-icon-box" style="width: 32px; height: 32px; border-radius: var(--radius-sm);">
            ${getFileIconSvg(meta.filename)}
          </div>
          <div style="overflow: hidden;">
            <div class="transfer-card-title" title="${meta.filename}">${meta.filename}</div>
            <div style="display: flex; gap: 0.4rem; align-items: center; margin-top: 2px;">
              <span class="transfer-direction-badge ${dirBadgeClass}">${dirLabel}</span>
              <span class="text-muted" style="font-size: 0.72rem;">${formatBytes(meta.fileSize)}</span>
            </div>
          </div>
        </div>
        <div style="text-align: right;">
          <span class="text-muted" id="pct_${transferId}" style="font-weight: 700; font-size: 0.95rem; color: var(--accent);">0%</span>
        </div>
      </div>

      <!-- Peer to Peer Wireless Animated Beam Stage -->
      <div class="p2p-beam-stage">
        <div class="p2p-device-node active">
          <div class="p2p-node-avatar" title="${meta.senderName}">
            ${getDeviceIconSvg(meta.senderName)}
          </div>
          <span class="p2p-node-name">${meta.senderName}</span>
        </div>

        <div class="p2p-beam-track">
          <div class="p2p-beam-pulses"></div>
          <div class="p2p-flying-packet">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          </div>
        </div>

        <div class="p2p-device-node active">
          <div class="p2p-node-avatar" title="${meta.receiverName}">
            ${getDeviceIconSvg(meta.receiverName)}
          </div>
          <span class="p2p-node-name">${meta.receiverName}</span>
        </div>
      </div>

      <div class="progress-track">
        <div class="progress-bar" id="bar_${transferId}"></div>
      </div>

      <div class="progress-meta">
        <span id="bytes_${transferId}">0 B / ${formatBytes(meta.fileSize)}</span>
        <span id="speed_${transferId}">Starting transfer...</span>
        <span id="eta_${transferId}">ETA: --</span>
      </div>
    `;

    return card;
  }

  function updateTransferProgress(transferId, loaded, total, speed, eta) {
    const pctEl = document.getElementById(`pct_${transferId}`);
    const barEl = document.getElementById(`bar_${transferId}`);
    const bytesEl = document.getElementById(`bytes_${transferId}`);
    const speedEl = document.getElementById(`speed_${transferId}`);
    const etaEl = document.getElementById(`eta_${transferId}`);

    const percent = Math.min(100, Math.round((loaded / Math.max(1, total)) * 100));
    if (pctEl) pctEl.textContent = `${percent}%`;
    if (barEl) barEl.style.width = `${percent}%`;
    if (bytesEl) bytesEl.textContent = `${formatBytes(loaded)} / ${formatBytes(total)}`;
    if (speedEl && speed > 0) speedEl.textContent = formatSpeed(speed);
    if (etaEl && eta !== undefined && eta !== null) {
      etaEl.textContent = eta > 0 ? `ETA: ${formatSeconds(eta)}` : 'Finalizing...';
    }
  }

  function completeTransferCard(transferId, data) {
    const card = document.getElementById(`card_${transferId}`);
    if (!card) return;

    const barEl = document.getElementById(`bar_${transferId}`);
    if (barEl) {
      barEl.style.width = '100%';
      barEl.style.backgroundColor = 'var(--success)';
    }
    const speedEl = document.getElementById(`speed_${transferId}`);
    if (speedEl) speedEl.innerHTML = `<span class="verifying-spinner"></span> Verifying SHA-256...`;

    setTimeout(() => {
      card.innerHTML = `
        <div class="transfer-card-header" style="margin-bottom: 0;">
          <div class="transfer-card-title-group">
            <div class="checkmark-wrap">
              <svg class="checkmark-svg" viewBox="0 0 52 52">
                <circle class="checkmark-circle" cx="26" cy="26" r="24"/>
                <path class="checkmark-check" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
              </svg>
            </div>
            <div style="overflow: hidden;">
              <div class="transfer-card-title">${data.filename}</div>
              <div class="text-muted" style="font-size: 0.75rem; margin-top: 2px;">
                ${formatBytes(data.file_size)} &bull; ${formatSpeed(data.avg_speed_bytes_sec || 0)} avg &bull;
                <span class="hash-preview" data-hash="${data.sha256}" data-name="${data.filename}" style="color: var(--accent); cursor: pointer;">
                  SHA-256: ${data.sha256.substring(0, 10)}...
                </span>
              </div>
            </div>
          </div>
          <div>
            <span class="badge badge-verified">
              Verified Lossless
            </span>
          </div>
        </div>
      `;
      bindHashModalTriggers();
    }, 450);
  }

  // --- Streaming Upload with Accurate Speed & Peer Notification ---

  function uploadFileWithProgress(file, direction) {
    const transferId = 'tx_' + Math.random().toString(36).substr(2, 9);
    state.localInitiatedTransfers.add(transferId);
    state.activeTransfers[transferId] = { file, startTime: Date.now() };

    const isLaptop = state.role === 'host';
    const peerDeviceName = state.connectedDevices[0]?.device_info?.device_name || (isLaptop ? 'Mobile Phone' : 'Host Laptop');
    const myDeviceName = isLaptop ? 'Host Laptop' : peerDeviceName;

    const senderName = isLaptop ? 'Host Laptop' : myDeviceName;
    const receiverName = isLaptop ? peerDeviceName : 'Host Laptop';

    // 1. Notify peer in real time that transfer started
    fetch('/api/transfers/notify-start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        transfer_id: transferId,
        filename: file.name,
        file_size: file.size,
        direction: direction,
        sender_device: senderName
      })
    }).catch(() => {});

    // 2. Render Outgoing Card on local client
    renderTransferCard(transferId, {
      filename: file.name,
      fileSize: file.size,
      direction: direction,
      senderName: senderName,
      receiverName: receiverName,
      isOutgoing: true
    });

    // 3. Initiate chunked streaming XHR upload
    const xhr = new XMLHttpRequest();
    const startTime = Date.now();
    let lastLoaded = 0;
    let lastTime = startTime;

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const now = Date.now();
        const timeDiff = (now - lastTime) / 1000;

        let currentSpeed = 0;
        let etaSeconds = 0;

        if (timeDiff >= 0.25) {
          const bytesDiff = e.loaded - lastLoaded;
          currentSpeed = bytesDiff / timeDiff;
          const remainingBytes = e.total - e.loaded;
          if (currentSpeed > 0) {
            etaSeconds = remainingBytes / currentSpeed;
          }
          lastLoaded = e.loaded;
          lastTime = now;

          // Notify peer of live progress
          fetch('/api/transfers/notify-progress', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...getAuthHeaders()
            },
            body: JSON.stringify({
              transfer_id: transferId,
              loaded: e.loaded,
              total: e.total,
              speed: currentSpeed,
              eta: Math.round(etaSeconds),
              direction: direction
            })
          }).catch(() => {});
        }

        updateTransferProgress(transferId, e.loaded, e.total, currentSpeed, Math.round(etaSeconds));
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const resp = JSON.parse(xhr.responseText);
        completeTransferCard(transferId, resp);
        showToast(`Transferred ${resp.filename} successfully`, 'success');
        loadHistory();
      } else {
        const card = document.getElementById(`card_${transferId}`);
        if (card) {
          card.innerHTML = `
            <div class="transfer-card-header">
              <span class="transfer-card-title">${file.name}</span>
              <span class="badge badge-mismatch">Upload Failed</span>
            </div>
            <p class="text-muted" style="font-size: 0.75rem; color: var(--danger); margin-top: 0.25rem;">
              Server error (${xhr.status}). Incomplete file was discarded.
            </p>
          `;
        }
        showToast(`Transfer failed for ${file.name}`, 'error');
      }
    });

    xhr.addEventListener('error', () => {
      const card = document.getElementById(`card_${transferId}`);
      if (card) {
        card.innerHTML = `
          <div class="transfer-card-header">
            <span class="transfer-card-title">${file.name}</span>
            <span class="badge badge-mismatch">Interrupted</span>
          </div>
        `;
      }
      showToast('Network transfer interrupted', 'error');
    });

    const formData = new FormData();
    formData.append('file', file);
    formData.append('direction', direction);

    xhr.open('POST', '/api/uploads');
    const token = state.token || state.hostToken;
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.setRequestHeader('X-AirLink-Token', token);
    }
    xhr.send(formData);
  }

  // --- Staged Files (Available for Mobile Download) ---

  async function loadStagedFiles() {
    try {
      const res = await fetch('/api/files', { headers: getAuthHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      state.stagedFiles = data.files || [];
      renderIncomingFiles(state.stagedFiles);
    } catch (err) {
      console.warn('Failed to load staged files:', err);
    }
  }

  function renderIncomingFiles(files) {
    if (!elements.incomingFilesList) return;
    if (!files || files.length === 0) {
      elements.incomingFilesList.innerHTML = '<div class="empty-state">No incoming files staged right now.</div>';
      return;
    }

    elements.incomingFilesList.innerHTML = '';
    const ul = document.createElement('ul');
    ul.className = 'file-preview-list';

    files.forEach(f => {
      const li = document.createElement('li');
      li.className = 'file-preview-item';
      li.innerHTML = `
        <div class="file-icon-box">
          ${getFileIconSvg(f.filename)}
        </div>
        <div class="file-info-col">
          <div class="file-title-text">${f.filename}</div>
          <div class="file-meta-subtext">
            ${f.file_size_formatted} &bull;
            <span class="hash-preview" data-hash="${f.sha256}" data-name="${f.filename}" style="cursor: pointer; color: var(--accent);">
              SHA-256: ${f.sha256.substring(0, 8)}...
            </span>
          </div>
        </div>
        <div>
          <a href="/api/files/${f.file_id}/download?token=${state.token || state.hostToken}" class="btn btn-primary btn-sm download-action-btn" download="${f.filename}">
            Download
          </a>
        </div>
      `;
      ul.appendChild(li);

      li.querySelector('.download-action-btn').addEventListener('click', () => {
        showToast(`Starting download: ${f.filename}`, 'info');
      });
    });

    elements.incomingFilesList.appendChild(ul);
    bindHashModalTriggers();
  }

  if (elements.refreshFilesBtn) elements.refreshFilesBtn.addEventListener('click', loadStagedFiles);

  // --- Transfer History & Filter Handling ---

  async function loadHistory() {
    try {
      const res = await fetch('/api/transfers', { headers: getAuthHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      state.historyItems = data.history || [];
      renderFilteredHistory();
    } catch (err) {
      console.warn('History load failed:', err);
    }
  }

  function renderFilteredHistory() {
    if (!elements.historyList) return;

    let items = state.historyItems;

    // Apply Segmented Filter
    if (state.historyFilter === 'sent') {
      items = items.filter(i => (state.role === 'host' ? i.direction === 'laptop_to_phone' : i.direction === 'phone_to_laptop'));
    } else if (state.historyFilter === 'received') {
      items = items.filter(i => (state.role === 'host' ? i.direction === 'phone_to_laptop' : i.direction === 'laptop_to_phone'));
    } else if (state.historyFilter === 'verified') {
      items = items.filter(i => i.verified);
    }

    // Apply Search Query
    if (state.historySearchQuery.trim()) {
      const q = state.historySearchQuery.toLowerCase();
      items = items.filter(i => i.filename.toLowerCase().includes(q));
    }

    if (!items || items.length === 0) {
      elements.historyList.innerHTML = '<div class="empty-state">No transfers match current filter.</div>';
      return;
    }

    elements.historyList.innerHTML = '';
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'history-item-card';

      const isOut = item.direction === 'laptop_to_phone';
      const dirBadge = isOut
        ? '<span class="history-dir-badge dir-sent">Sent &uarr;</span>'
        : '<span class="history-dir-badge dir-received">Received &darr;</span>';

      const integrityBadge = item.verified
        ? `<span class="badge badge-verified" style="font-size: 0.7rem; padding: 2px 6px;">Verified</span>`
        : `<span class="badge badge-calculated" style="font-size: 0.7rem; padding: 2px 6px;">Calculated</span>`;

      card.innerHTML = `
        <div class="history-card-top">
          <div class="history-card-title-group">
            <div class="file-icon-box" style="width: 32px; height: 32px; border-radius: var(--radius-sm);">
              ${getFileIconSvg(item.filename)}
            </div>
            <div>
              <div class="history-card-filename" title="${item.filename}">${item.filename}</div>
              <div class="history-card-date">${item.created_at || 'Just now'}</div>
            </div>
          </div>
          <div>
            ${dirBadge}
          </div>
        </div>

        <div class="history-card-meta">
          <span>${item.file_size_formatted}</span>
          <span>&bull;</span>
          <span>${item.speed_formatted}</span>
          <span>&bull;</span>
          ${integrityBadge}
          <span class="hash-preview" data-hash="${item.sha256_hash}" data-name="${item.filename}" title="View full SHA-256 hash" style="cursor: pointer; color: var(--accent); font-family: var(--font-mono); font-size: 0.72rem;">
            ${item.sha256_hash.substring(0, 8)}...
          </span>
        </div>

        ${item.has_local_file ? `
          <div style="margin-top: 0.6rem; text-align: right;">
            <a href="/api/transfers/${item.transfer_id}/download?token=${state.token || state.hostToken}" class="btn btn-secondary btn-sm" download="${item.filename}">
              Download Copy
            </a>
          </div>
        ` : ''}
      `;
      elements.historyList.appendChild(card);
    });

    bindHashModalTriggers();
  }

  // Segmented Control Buttons
  document.querySelectorAll('.segmented-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.segmented-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.historyFilter = btn.getAttribute('data-filter') || 'all';
      renderFilteredHistory();
    });
  });

  // History Search
  if (elements.historySearchInput) {
    elements.historySearchInput.addEventListener('input', (e) => {
      state.historySearchQuery = e.target.value;
      renderFilteredHistory();
    });
  }

  // Clear History
  if (elements.clearHistoryBtn) {
    elements.clearHistoryBtn.addEventListener('click', async () => {
      if (!confirm('Clear all transfer history records?')) return;
      try {
        const res = await fetch('/api/transfers', {
          method: 'DELETE',
          headers: getAuthHeaders()
        });
        if (res.ok) {
          showToast('Transfer history cleared', 'info');
          loadHistory();
        }
      } catch (e) {
        showToast('Failed to clear history', 'error');
      }
    });
  }

  // --- SHA-256 Checksum Inspection Modal ---

  function bindHashModalTriggers() {
    document.querySelectorAll('.hash-preview').forEach(el => {
      el.onclick = (e) => {
        e.preventDefault();
        const hash = el.getAttribute('data-hash');
        const name = el.getAttribute('data-name');
        if (elements.modalFileTitle) elements.modalFileTitle.textContent = name;
        if (elements.modalHashContent) elements.modalHashContent.textContent = hash;
        if (elements.checksumModal) elements.checksumModal.classList.add('active');
      };
    });
  }

  if (elements.closeChecksumModal) elements.closeChecksumModal.onclick = () => elements.checksumModal.classList.remove('active');
  if (elements.dismissChecksumModal) elements.dismissChecksumModal.onclick = () => elements.checksumModal.classList.remove('active');
  if (elements.checksumModal) {
    elements.checksumModal.onclick = (e) => {
      if (e.target === elements.checksumModal) elements.checksumModal.classList.remove('active');
    };
  }

  if (elements.copyHashBtn) {
    elements.copyHashBtn.onclick = () => {
      navigator.clipboard.writeText(elements.modalHashContent.textContent.trim());
      elements.copyHashBtn.textContent = 'Copied!';
      setTimeout(() => elements.copyHashBtn.textContent = 'Copy Hash', 1500);
      showToast('SHA-256 hash copied to clipboard', 'info');
    };
  }

  // --- Help Modal ---

  if (elements.helpBtn && elements.helpModal) {
    elements.helpBtn.onclick = () => elements.helpModal.classList.add('active');
    if (elements.closeHelpModal) elements.closeHelpModal.onclick = () => elements.helpModal.classList.remove('active');
    if (elements.dismissHelpModal) elements.dismissHelpModal.onclick = () => elements.helpModal.classList.remove('active');
    elements.helpModal.onclick = (e) => {
      if (e.target === elements.helpModal) elements.helpModal.classList.remove('active');
    };
  }

  // --- Copy URL & Rescan Network Buttons ---

  if (elements.copyUrlBtn && elements.accessUrlText) {
    elements.copyUrlBtn.onclick = () => {
      navigator.clipboard.writeText(elements.accessUrlText.textContent.trim());
      elements.copyUrlBtn.textContent = 'Copied!';
      setTimeout(() => elements.copyUrlBtn.textContent = 'Copy', 1500);
      showToast('Connection URL copied to clipboard', 'info');
    };
  }

  if (elements.refreshNetworkBtn) {
    elements.refreshNetworkBtn.onclick = async () => {
      elements.refreshNetworkBtn.disabled = true;
      showToast('Rescanning Wi-Fi & network adapters...', 'info');
      await loadNetworkInfo();
      setTimeout(() => {
        elements.refreshNetworkBtn.disabled = false;
        showToast('Network information refreshed', 'success');
      }, 500);
    };
  }

  if (elements.refreshCodeLink) {
    elements.refreshCodeLink.addEventListener('click', (e) => {
      e.preventDefault();
      refreshPairingCode();
    });
  }

  // --- WebSocket Real-time Event Handling ---

  function initWebSocket() {
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = state.token || state.hostToken || '';
    const wsUrl = `${protocol}//${window.location.host}/ws?token=${token}`;

    try {
      state.ws = new WebSocket(wsUrl);

      state.ws.onopen = () => {
        state.wsConnected = true;
      };

      state.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleWebSocketEvent(msg);
        } catch (e) {}
      };

      state.ws.onclose = () => {
        state.wsConnected = false;
        setTimeout(initWebSocket, 3000); // Auto reconnect
      };

      state.ws.onerror = () => {
        state.wsConnected = false;
      };
    } catch (err) {
      console.warn('WebSocket init failed:', err);
    }
  }

  function handleWebSocketEvent(msg) {
    const { event, data } = msg;

    if (event === 'device_connected') {
      if (state.role === 'host') {
        setConnectionState('CONNECTED', data.device);
        showToast(`Device connected: ${data.device.device_name}`, 'success');
      }
    } else if (event === 'device_disconnected') {
      if (state.role === 'host') {
        setConnectionState('WAITING_FOR_DEVICE');
        showToast('Device disconnected', 'info');
      }
    } else if (event === 'pairing_requested') {
      if (state.role === 'host') {
        setConnectionState('PAIRING_PENDING');
        checkSessionState();
      }
    } else if (event === 'pairing_decision') {
      if (state.pendingRequestId && data.request_id === state.pendingRequestId) {
        if (data.status === 'approved' && data.token) {
          state.token = data.token;
          localStorage.setItem('airlink_token', data.token);
          checkSessionState();
        }
      } else if (state.role === 'host') {
        const banner = document.querySelector(`[data-id="${data.request_id}"]`);
        if (banner) banner.remove();
        checkSessionState();
      }
    } else if (event === 'code_refreshed') {
      state.pairingCode = data.pairing_code;
      state.codeRemaining = data.remaining_seconds;
      if (elements.pairingCodeDisplay) elements.pairingCodeDisplay.textContent = data.pairing_code;
      startCodeCountdown();
    } else if (event === 'transfer_started') {
      // Both sides see the transfer!
      if (!state.localInitiatedTransfers.has(data.transfer_id)) {
        const myName = state.role === 'host' ? 'Host Laptop' : 'Mobile Phone';
        renderTransferCard(data.transfer_id, {
          filename: data.filename,
          fileSize: data.file_size,
          direction: data.direction,
          senderName: data.sender_device || 'Peer Device',
          receiverName: myName,
          isOutgoing: false
        });
        showToast(`Incoming file: ${data.filename}`, 'info');
      }
    } else if (event === 'transfer_progress') {
      // Receiver updates progress in lockstep with sender
      if (!state.localInitiatedTransfers.has(data.transfer_id)) {
        updateTransferProgress(data.transfer_id, data.loaded, data.total, data.speed, data.eta);
      }
    } else if (event === 'transfer_completed') {
      completeTransferCard(data.transfer_id, data);
      loadHistory();
      loadStagedFiles();
    } else if (event === 'transfer_failed') {
      const card = document.getElementById(`card_${data.transfer_id}`);
      if (card) {
        card.innerHTML = `
          <div class="transfer-card-header">
            <span class="transfer-card-title">${data.filename || 'Transfer'}</span>
            <span class="badge badge-mismatch">Failed</span>
          </div>
        `;
      }
    } else if (event === 'files_staged_updated') {
      renderIncomingFiles(data.staged_files || []);
      if (state.role === 'client') {
        showToast('New files available from laptop for download', 'info');
      }
    } else if (event === 'history_cleared') {
      state.historyItems = [];
      renderFilteredHistory();
    } else if (event === 'session_disconnected') {
      if (data.token === state.token) {
        localStorage.removeItem('airlink_token');
        location.reload();
      }
    }
  }

  // --- App Initialization ---

  initTheme();
  loadNetworkInfo();
  checkSessionState().then(() => {
    initWebSocket();
  });

  // Host background polling: check pending pairing requests every 1.5s as an ultra-fast fallback
  setInterval(() => {
    if (state.role === 'host') {
      fetch('/api/session/state', { headers: getAuthHeaders() })
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data && data.pending_requests && data.pending_requests.length > 0) {
            renderPendingPairingRequests(data.pending_requests);
          }
        })
        .catch(() => {});
    }
  }, 1500);

})();
