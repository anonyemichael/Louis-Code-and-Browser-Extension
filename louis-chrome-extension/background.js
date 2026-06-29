/**
 * Louis Web Agent — Background Service Worker
 * 
 * Acts as the central message broker between:
 *   - Side Panel UI (chat interface)
 *   - Content Script (DOM interaction)
 *   - Louis CLI (via WebSocket on ws://localhost:7865)
 * 
 * Manifest V3 service worker — event-driven, non-persistent.
 */

// ── Configuration ─────────────────────────────────────────────────────────
const WS_URL = 'ws://localhost:7865';
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS  = 30000;
const HEARTBEAT_MS      = 15000;

// ── State ─────────────────────────────────────────────────────────────────
let ws = null;
let wsReconnectDelay = RECONNECT_BASE_MS;
let wsReconnectTimer = null;
let heartbeatTimer = null;
let sidePanelPort = null;
let connectionStatus = 'disconnected';

// ── Slide Capture State ──
let capturedSlides = [];
let slideCaptureTimer = null;
let lastSlideImageData = null;

// ── Side Panel Click → Open ───────────────────────────────────────────────
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
  .catch(e => console.warn('sidePanel behavior error:', e));

// ── Side Panel Communication ──────────────────────────────────────────────
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === 'sidepanel') {
    sidePanelPort = port;

    port.onMessage.addListener((msg) => {
      handleSidePanelMessage(msg, port);
    });

    port.onDisconnect.addListener(() => {
      sidePanelPort = null;
    });

    // Send current status immediately
    port.postMessage({
      type: 'connection_status',
      status: connectionStatus,
    });

    // Ensure WebSocket is connected
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    }
  }
});

function handleSidePanelMessage(msg, port) {
  switch (msg.type) {
    case 'get_status':
      port.postMessage({
        type: 'connection_status',
        status: connectionStatus,
      });
      break;

    case 'user_message':
      handleUserMessage(msg.text);
      break;

    case 'start_slide_capture':
      handleStartSlideCapture({ from_sidepanel: true });
      break;

    case 'stop_slide_capture':
      handleStopSlideCapture({ from_sidepanel: true });
      break;

    default:
      console.log('Unknown side panel message:', msg);
  }
}

function notifySidePanel(message) {
  if (sidePanelPort) {
    try {
      sidePanelPort.postMessage(message);
    } catch (e) {
      console.warn('Side panel port disconnected:', e);
      sidePanelPort = null;
    }
  }
}

// ── WebSocket Connection ──────────────────────────────────────────────────
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  setConnectionStatus('connecting');

  try {
    ws = new WebSocket(WS_URL);
  } catch (e) {
    console.error('WebSocket constructor failed:', e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log('[Louis] WebSocket connected');
    wsReconnectDelay = RECONNECT_BASE_MS;
    setConnectionStatus('connected');
    startHeartbeat();

    // Send initial handshake with tab context
    sendCurrentPageContext();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerMessage(data);
    } catch (e) {
      console.error('Failed to parse server message:', e, event.data);
    }
  };

  ws.onerror = (event) => {
    console.error('[Louis] WebSocket error:', event);
  };

  ws.onclose = (event) => {
    console.log('[Louis] WebSocket closed:', event.code, event.reason);
    ws = null;
    stopHeartbeat();
    setConnectionStatus('disconnected');
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  if (wsReconnectTimer) clearTimeout(wsReconnectTimer);

  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    connectWebSocket();
  }, wsReconnectDelay);

  // Exponential backoff
  wsReconnectDelay = Math.min(wsReconnectDelay * 1.5, RECONNECT_MAX_MS);
}

function setConnectionStatus(status) {
  connectionStatus = status;
  notifySidePanel({ type: 'connection_status', status });
}

// ── Heartbeat ─────────────────────────────────────────────────────────────
function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: 'ping' }));
    }
  }, HEARTBEAT_MS);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

// ── Send to Louis Server ──────────────────────────────────────────────────
function sendToServer(message) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
    return true;
  }
  notifySidePanel({
    type: 'error',
    text: 'Not connected to Louis CLI. Start the server with /browser command.',
  });
  return false;
}

// ── Handle User Messages ──────────────────────────────────────────────────
async function handleUserMessage(text) {
  // Get current page context to send along
  let pageContext = {};
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      pageContext = {
        url: tab.url,
        title: tab.title,
        tabId: tab.id,
      };
    }
  } catch (e) {
    console.warn('Could not get tab context:', e);
  }

  // Send to Louis server
  sendToServer({
    action: 'user_message',
    text: text,
    page_context: pageContext,
  });
}

// ── Handle Server Messages ────────────────────────────────────────────────
function handleServerMessage(data) {
  switch (data.action) {
    case 'pong':
      // Heartbeat acknowledged
      break;

    case 'response':
      notifySidePanel({
        type: 'louis_response',
        text: data.text || '',
      });
      break;

    case 'action_start':
      notifySidePanel({
        type: 'action_start',
        text: data.text || 'Working...',
      });
      break;

    case 'action_complete':
      notifySidePanel({
        type: 'action_complete',
        text: data.text || 'Done',
      });
      break;

    case 'action_error':
      notifySidePanel({
        type: 'action_error',
        text: data.text || 'Action failed',
      });
      break;

    // ── Browser actions from Louis ──────────────────────────────────────
    case 'click':
      executeContentAction('click', data);
      break;

    case 'type':
      executeContentAction('type', data);
      break;

    case 'scroll':
      executeContentAction('scroll', data);
      break;

    case 'read_page':
      executeContentAction('read_page', data);
      break;

    case 'navigate':
      handleNavigate(data);
      break;

    case 'new_tab':
      handleNewTab(data);
      break;

    case 'get_elements':
      executeContentAction('get_elements', data);
      break;

    case 'set_cookie':
    case 'set_user_agent':
    case 'wait_element':
      executeContentAction(data.action, data);
      break;

    case 'screenshot':
      handleScreenshot(data);
      break;

    case 'multi_action':
    case 'batch_browser_actions':
      handleMultiAction(data);
      break;

    case 'start_slide_capture':
      handleStartSlideCapture(data);
      break;

    case 'stop_slide_capture':
      handleStopSlideCapture(data);
      break;

    default:
      console.log('Unknown server action:', data);
  }
}

// ── Execute Content Script Actions ────────────────────────────────────────
async function dispatchContentAction(action, data) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      return { success: false, error: 'No active tab' };
    }

    if (tab.url && (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://'))) {
      return { success: false, error: 'Cannot interact with browser internal pages' };
    }

    const results = await chrome.tabs.sendMessage(tab.id, {
      type: 'louis_action',
      action: action,
      data: data,
    });

    return {
      success: results?.success ?? false,
      data: results?.data || null,
      error: results?.error || null,
    };
  } catch (e) {
    return { success: false, error: e.message || 'Content script error' };
  }
}

async function executeContentAction(action, data) {
  const result = await dispatchContentAction(action, data);
  sendToServer({
    action: 'action_result',
    original_action: action,
    success: result.success,
    data: result.data,
    error: result.error,
  });
}

// ── Multi Action ──────────────────────────────────────────────────────────
async function handleMultiAction(data) {
  try {
    let results = [];
    const actions = data.actions || [];
    let success = true;

    for (const act of actions) {
      let subResult = await dispatchContentAction(act.action, act);
      results.push({ action: act.action, result: subResult });
      if (!subResult.success) {
        success = false;
        break;
      }
      // Wait briefly between actions to allow the DOM to react
      await new Promise(r => setTimeout(r, 300));
    }

    sendToServer({
      action: 'action_result',
      original_action: data.action || 'multi_action',
      success: success,
      data: { results: results },
    });
  } catch (e) {
    sendToServer({
      action: 'action_result',
      original_action: data.action || 'multi_action',
      success: false,
      error: e.message,
    });
  }
}

// ── Navigation ────────────────────────────────────────────────────────────
async function handleNavigate(data) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;

    notifySidePanel({ type: 'action_start', text: `Navigating to ${data.url}...` });

    await chrome.tabs.update(tab.id, { url: data.url });

    // Wait for page to load, then report back
    const listener = (tabId, changeInfo) => {
      if (tabId === tab.id && changeInfo.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        sendToServer({
          action: 'action_result',
          original_action: 'navigate',
          success: true,
          data: { url: data.url },
        });
        notifySidePanel({ type: 'action_complete', text: `Navigated to ${data.url}` });

        // Update page context
        chrome.tabs.get(tabId, (updatedTab) => {
          if (updatedTab) {
            notifySidePanel({
              type: 'page_context',
              title: updatedTab.title,
              url: updatedTab.url,
            });
          }
        });
      }
    };
    chrome.tabs.onUpdated.addListener(listener);

    // Timeout after 15 seconds
    setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
    }, 15000);

  } catch (e) {
    sendToServer({
      action: 'action_result',
      original_action: 'navigate',
      success: false,
      error: e.message,
    });
  }
}

// ── New Tab ───────────────────────────────────────────────────────────────
async function handleNewTab(data) {
  try {
    const targetUrl = data.url ? data.url.trim() : undefined;
    if (targetUrl) {
      notifySidePanel({ type: 'action_start', text: `Opening new tab: ${targetUrl}...` });
    } else {
      notifySidePanel({ type: 'action_start', text: `Opening new tab...` });
    }

    const newTab = await chrome.tabs.create(targetUrl ? { url: targetUrl } : {});

    if (targetUrl) {
      const listener = (tabId, changeInfo) => {
        if (tabId === newTab.id && changeInfo.status === 'complete') {
          chrome.tabs.onUpdated.removeListener(listener);
          sendToServer({
            action: 'action_result',
            original_action: 'new_tab',
            success: true,
            data: { url: targetUrl, tab_opened: true },
          });
          notifySidePanel({ type: 'action_complete', text: `Opened new tab: ${targetUrl}` });

          chrome.tabs.get(tabId, (updatedTab) => {
            if (updatedTab) {
              notifySidePanel({
                type: 'page_context',
                title: updatedTab.title,
                url: updatedTab.url,
              });
            }
          });
        }
      };
      chrome.tabs.onUpdated.addListener(listener);

      setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(listener);
      }, 15000);
    } else {
      sendToServer({
        action: 'action_result',
        original_action: 'new_tab',
        success: true,
        data: { tab_opened: true },
      });
      notifySidePanel({ type: 'action_complete', text: `Opened new tab` });
    }
  } catch (e) {
    sendToServer({
      action: 'action_result',
      original_action: 'new_tab',
      success: false,
      error: e.message,
    });
  }
}

// ── Screenshot ────────────────────────────────────────────────────────────
async function handleScreenshot(data) {
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, {
      format: 'png',
      quality: 80,
    });

    sendToServer({
      action: 'action_result',
      original_action: 'screenshot',
      success: true,
      data: { image: dataUrl },
    });
  } catch (e) {
    sendToServer({
      action: 'action_result',
      original_action: 'screenshot',
      success: false,
      error: e.message,
    });
  }
}

// ── Slide Capture ─────────────────────────────────────────────────────────
async function computeImageHash(dataUrl) {
  try {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);
    // Downscale to 32x32 to get a basic pixel representation that ignores minor video compression artifacts
    const canvas = new OffscreenCanvas(32, 32);
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0, 32, 32);
    return ctx.getImageData(0, 0, 32, 32).data;
  } catch (e) {
    console.error('Failed to hash image:', e);
    return null;
  }
}

function computeImageDiff(data1, data2) {
  if (!data1 || !data2 || data1.length !== data2.length) return 100;
  let diff = 0;
  for (let i = 0; i < data1.length; i += 4) {
    // Only compare RGB, ignore Alpha
    diff += Math.abs(data1[i] - data2[i]);
    diff += Math.abs(data1[i+1] - data2[i+1]);
    diff += Math.abs(data1[i+2] - data2[i+2]);
  }
  return (diff / (32 * 32 * 3 * 255)) * 100; // Returns percentage difference (0-100)
}

async function handleStartSlideCapture(data) {
  if (slideCaptureTimer) {
    const result = { success: false, error: 'Slide capture is already running.' };
    if (data.from_sidepanel) notifySidePanel({ type: 'action_error', text: result.error });
    else sendToServer({ action: 'action_result', original_action: 'start_slide_capture', ...result });
    return;
  }

  capturedSlides = [];
  lastSlideImageData = null;
  notifySidePanel({ type: 'action_start', text: 'Starting continuous slide capture...' });

  slideCaptureTimer = setInterval(async () => {
    try {
      const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 80 });
      if (!dataUrl) return;

      const newHashData = await computeImageHash(dataUrl);
      if (!lastSlideImageData) {
        // First slide
        capturedSlides.push(dataUrl);
        lastSlideImageData = newHashData;
        notifySidePanel({ type: 'action_complete', text: `Captured slide 1` });
      } else {
        const diff = computeImageDiff(lastSlideImageData, newHashData);
        // If image is more than 3% different, we consider it a new slide
        if (diff > 3.0) {
          capturedSlides.push(dataUrl);
          lastSlideImageData = newHashData;
          notifySidePanel({ type: 'action_complete', text: `Captured slide ${capturedSlides.length}` });
        }
      }
    } catch (e) {
      console.warn('Slide capture interval error:', e);
    }
  }, 5000);

  const result = { success: true, data: { status: 'capturing' } };
  if (!data.from_sidepanel) {
    sendToServer({ action: 'action_result', original_action: 'start_slide_capture', ...result });
  }
}

async function handleStopSlideCapture(data) {
  if (!slideCaptureTimer) {
    const result = { success: false, error: 'Slide capture is not running.' };
    if (data.from_sidepanel) notifySidePanel({ type: 'action_error', text: result.error });
    else sendToServer({ action: 'action_result', original_action: 'stop_slide_capture', ...result });
    return;
  }

  clearInterval(slideCaptureTimer);
  slideCaptureTimer = null;
  lastSlideImageData = null;

  if (capturedSlides.length === 0) {
    const result = { success: true, data: { message: 'Stopped. No slides were captured.' } };
    if (data.from_sidepanel) notifySidePanel({ type: 'action_complete', text: result.data.message });
    else sendToServer({ action: 'action_result', original_action: 'stop_slide_capture', ...result });
    return;
  }

  try {
    notifySidePanel({ type: 'action_start', text: `Generating HTML with ${capturedSlides.length} slides...` });
    
    // Generate HTML document
    const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Captured Slides</title>
  <style>
    body { font-family: sans-serif; background: #111; color: #fff; padding: 20px; text-align: center; }
    .slide { margin-bottom: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
    img { max-width: 100%; height: auto; display: block; margin: 0 auto; }
    h2 { margin-bottom: 10px; color: #ddd; }
  </style>
</head>
<body>
  <h1>Captured Slides</h1>
  <p>Total Slides: ${capturedSlides.length}</p>
  ${capturedSlides.map((src, i) => `
    <div class="slide">
      <h2>Slide ${i + 1}</h2>
      <img src="${src}">
    </div>
  `).join('')}
</body>
</html>`;

    // Convert to blob and create object URL
    const blob = new Blob([html], { type: 'text/html' });
    
    // Workaround for MV3 Service Workers: Since URL.createObjectURL is not available,
    // we use a Data URL for the HTML file download instead.
    const reader = new FileReader();
    reader.onloadend = () => {
      const b64Html = reader.result;
      chrome.downloads.download({
        url: b64Html,
        filename: 'zoom_slides.html',
        saveAs: true
      }, (downloadId) => {
        if (chrome.runtime.lastError) {
          console.error(chrome.runtime.lastError);
        }
        const result = { success: true, data: { message: \`Stopped. Downloaded \${capturedSlides.length} slides as zoom_slides.html\` } };
        if (data.from_sidepanel) notifySidePanel({ type: 'action_complete', text: result.data.message });
        else sendToServer({ action: 'action_result', original_action: 'stop_slide_capture', ...result });
        
        // Clear memory
        capturedSlides = [];
      });
    };
    reader.readAsDataURL(blob);

  } catch (e) {
    const result = { success: false, error: 'Failed to save slides: ' + e.message };
    if (data.from_sidepanel) notifySidePanel({ type: 'action_error', text: result.error });
    else sendToServer({ action: 'action_result', original_action: 'stop_slide_capture', ...result });
  }
}

// ── Send Page Context on Tab Change ───────────────────────────────────────
async function sendCurrentPageContext() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      sendToServer({
        action: 'page_context',
        url: tab.url,
        title: tab.title,
        tabId: tab.id,
      });

      notifySidePanel({
        type: 'page_context',
        title: tab.title,
        url: tab.url,
      });
    }
  } catch (e) {
    console.warn('Could not get page context:', e);
  }
}

// Listen for tab switches
chrome.tabs.onActivated.addListener(() => {
  sendCurrentPageContext();
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === 'complete') {
    sendCurrentPageContext();
  }
});

// ── Initial connection attempt ────────────────────────────────────────────
connectWebSocket();
