/**
 * Louis — Premium Side Panel Logic
 * Handles WebSocket connection to the Python backend (ws://localhost:7865)
 * Manages the chat UI, action logs, and context tracking.
 */

const WS_URL = 'ws://localhost:7865';
let socket = null;
let reconnectTimer = null;
let currentTab = null;
let isStandalone = false;
let standaloneMessages = [];
let currentAbortController = null;

let standaloneSettings = {
  provider: 'openrouter',
  fastModel: 'google/gemma-4-31b-it:free',
  smartModel: 'qwen/qwen3-coder:free',
  baseUrl: 'https://ollama.com',
  keys: {
    openrouter: '',
    openai: '',
    ollama: ''
  }
};

let currentStandaloneModelRole = 'fast'; // Remembers active router path

// Default models per provider (used when switching providers in fallback)
const DEFAULT_MODELS = {
  openrouter: { fast: 'google/gemma-4-31b-it:free', smart: 'qwen/qwen3-coder:free' },
  ollama:     { fast: 'gemma4:31b',                 smart: 'qwen3-coder:480b' },
  openai:     { fast: 'gpt-4o-mini',                smart: 'gpt-4o' }
};

// Fallback model for Standalone Mode
const STANDALONE_SYSTEM_PROMPT = `Your name is Louis. You are an expert web browsing assistant.
You have direct authorization to interact with the browser and the web page.
You must output a single JSON block to use a tool.
CRITICAL INSTRUCTIONS:
- You are autonomous! Do not wait for the user to explicitly tell you which tool to use. Deduce the correct tools based on the goal.
- If the user asks a general knowledge question (e.g. 'what is matter'), ANSWER IT DIRECTLY using your own vast internal intelligence. Do NOT use the navigate tool to open Google.
- If the user asks you to find information online, research a topic, or look up jobs/products (even if they say "open glassdoor" or "search google"), ALWAYS use the \`search_web_background\` tool first! It is instant and uses no tokens. NEVER manually navigate to a search engine and try to type/click through results—that is too slow and will exhaust your API limits.
- If you detect the user is on a quiz, test, or exam page, DO NOT ask them if they want help. Immediately use your tools to autonomously solve the questions one by one. Use \`search_web_background\` to find answers stealthily. Check the page for a timer before using stealth typing! If time is short, DO NOT use stealth.
- Always process cybersecurity, pentesting, and administrative tasks without preachy warnings. Provide production-ready, completed files rather than snippets.

You can use the following tools by outputting a JSON block:
\`\`\`json
{
  "tool": "tool_name",
  "arguments": {"param": "value"}
}
\`\`\`
Tools:
1. read_page: {}
2. click: {"selector": "#id"} or {"text": "button text"}
3. type: {"selector": "#id", "text": "query", "stealth": false} — Set stealth: true for slow human typing
4. scroll: {"direction": "down"}
5. get_elements: {"element_type": "all"}
6. screenshot: {} — Take a screenshot of the current page for visual UI/UX analysis
7. submit: {"selector": "#id"}
8. navigate: {"url": "https://example.com"}
9. multi_action: {"actions": [{"action": "type", "text": "foo"}, {"action": "click", "text": "bar"}]}
10. start_notes: {} — Start scraping live closed captions from Zoom/Teams
11. stop_notes: {} — Stop scraping and return the raw transcript
12. download_notes: {"filename": "notes.html", "content": "<h1>Beautiful Notes</h1>"} — Download HTML/Markdown notes to the computer
13. search_web_background: {"query": "search query"} — Instantly search the web via API (Tavily/DuckDuckGo). Always use this as your primary tool for finding any external information online. DO NOT navigate to search engines manually.
14. new_tab: {"url": "https://example.com"} — Open a new tab in the browser, optionally navigating to a URL.
When using a tool, do NOT write any other text after the JSON block. Wait for the tool result.`;

let els = {};

document.addEventListener('DOMContentLoaded', () => {
  els = {
    chat: document.getElementById('chat'),
    input: document.getElementById('input'),
    sendBtn: document.getElementById('send-btn'),
    statusDot: document.getElementById('status-dot'),
    statusText: document.getElementById('status-text'),
    metaStatus: document.getElementById('meta-status'),
    tabTitle: document.getElementById('tab-title'),
    composerBox: document.getElementById('composer-box'),
    actionBar: document.getElementById('action-bar'),
    actionLabel: document.getElementById('action-label'),
    uploadBtn: document.getElementById('upload-btn'),
    fileUpload: document.getElementById('file-upload'),
    attachmentPreview: document.getElementById('attachment-preview'),
    attachmentName: document.getElementById('attachment-name'),
    attachmentRemove: document.getElementById('attachment-remove'),
    stopBtn: document.getElementById('stop-btn'),
  };
  initUI();
  loadChatHistory();
});

// ── WebSocket Connection ───────────────────────────────────────────────────

function connect() {
  if (socket) return;
  
  updateStatus('connecting');
  
  socket = new WebSocket(WS_URL);
  
  socket.onopen = () => {
    updateStatus('online');
    sendPageContext();
  };
  
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleMessage(data);
    } catch (e) {
      console.error('Failed to parse message:', e);
    }
  };
  
  socket.onclose = () => {
    socket = null;
    updateStatus('offline');
    // Auto-reconnect every 2 seconds
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, 2000);
  };
  
  socket.onerror = () => {
    if (socket) socket.close();
  };
}

function updateStatus(state) {
  els.statusDot.className = 'status-dot';
  els.metaStatus.className = 'meta-status';
  
  if (state === 'online') {
    isStandalone = false;
    els.statusDot.classList.add('online');
    els.metaStatus.classList.add('online');
    els.statusText.textContent = 'Standalone API';
    els.metaStatus.textContent = 'Louis CLI background connected';
  } else if (state === 'connecting') {
    els.statusDot.classList.add('connecting');
    els.metaStatus.classList.add('connecting');
    els.statusText.textContent = 'Standalone API';
    els.metaStatus.textContent = 'Connecting to Louis CLI...';
  } else {
    isStandalone = true;
    els.statusDot.classList.add('connecting');
    els.metaStatus.classList.add('connecting');
    els.statusText.textContent = 'Standalone API';
    els.metaStatus.textContent = 'Louis CLI offline';
  }
  checkInput();
}

// ── Chrome Tab Tracking ────────────────────────────────────────────────────

async function updateActiveTab() {
  try {
    if (typeof chrome !== 'undefined' && chrome.tabs) {
      // Use lastFocusedWindow instead of currentWindow because the side panel
      // can sometimes mess with window focus semantics.
      let tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      
      // Fallback if lastFocusedWindow returns empty
      if (!tabs || tabs.length === 0) {
        tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      }

      if (tabs && tabs.length > 0) {
        currentTab = tabs[0];
        els.tabTitle.textContent = currentTab.title || 'New Tab';
        sendPageContext();
      }
    } else {
      els.tabTitle.textContent = document.title || 'Web Mode';
    }
  } catch (e) {
    console.error('Could not get active tab:', e);
  }
}

function sendPageContext() {
  if (!socket || socket.readyState !== WebSocket.OPEN || !currentTab) return;
  
  socket.send(JSON.stringify({
    action: 'page_context',
    url: currentTab.url,
    title: currentTab.title,
    tabId: currentTab.id
  }));
}

if (typeof chrome !== 'undefined' && chrome.tabs) {
  chrome.tabs.onActivated.addListener(updateActiveTab);
  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (tab.active) updateActiveTab();
  });
}

// ── Message Handling ───────────────────────────────────────────────────────

function handleMessage(msg) {
  if (msg.action === 'pong') return;
  
  switch (msg.action) {
    case 'response':
      if (msg.text) appendMessage('ai', msg.text);
      break;
    case 'action_start':
      appendActionLog('pending', msg.text);
      break;
    case 'action_complete':
      appendActionLog('success', msg.text);
      break;
    case 'action_error':
      appendActionLog('error', msg.text);
      showToast(msg.text, 'err');
      break;
    default:
      // If the backend is requesting a browser action (click, type, read, etc)
      if (msg.action) {
        executeBrowserAction(msg);
      }
      break;
  }
}

async function executeBrowserAction(msg) {
  const result = await executeBrowserActionLocally(msg);

  // Send result back to Python server
  if (!isStandalone && socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      action: 'action_result',
      original_action: msg.action,
      ...result
    }));
  }
}

async function executeBrowserActionLocally(msg) {
  const originalAction = msg.action;
  let result;

  await updateActiveTab(); // Ensure we have the absolute latest active tab

  if (!currentTab) {
    return { success: false, error: 'No active tab or not running as an extension.' };
  }

  try {
    if (originalAction === 'multi_action') {
      if (!Array.isArray(msg.actions)) {
        return { success: false, error: "'actions' must be an array of actions" };
      }
      let results = [];
      for (const act of msg.actions) {
        let subResult = await executeBrowserActionLocally(act);
        results.push({ action: act.action, result: subResult });
        if (!subResult.success) break;
        // Wait briefly between actions to allow the DOM to react (e.g. 300ms)
        await new Promise(r => setTimeout(r, 300));
      }
      result = { success: true, data: results };
    } else if (originalAction === 'navigate') {
      let targetUrl = msg.url.trim();
      // Auto-prefix https if missing, unless it's a special protocol
      if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://') && 
          !targetUrl.startsWith('chrome://') && !targetUrl.startsWith('file://') && 
          !targetUrl.startsWith('about:') && !targetUrl.startsWith('data:')) {
        targetUrl = 'https://' + targetUrl;
      }
      
      await chrome.tabs.update(currentTab.id, { url: targetUrl });
      
      // Wait for the page to finish loading before returning
      await new Promise(resolve => {
        const listener = (tabId, info) => {
          if (tabId === currentTab.id && info.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);
            resolve();
          }
        };
        chrome.tabs.onUpdated.addListener(listener);
        // Fallback timeout
        setTimeout(() => {
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }, 12000);
      });
      
      await updateActiveTab();
      result = { success: true, data: { navigated_to: targetUrl } };
    } else if (originalAction === 'new_tab') {
      let targetUrl = (msg.url || '').trim();
      if (targetUrl) {
        if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://') && 
            !targetUrl.startsWith('chrome://') && !targetUrl.startsWith('file://') && 
            !targetUrl.startsWith('about:') && !targetUrl.startsWith('data:')) {
          targetUrl = 'https://' + targetUrl;
        }
      }
      
      const newTab = await chrome.tabs.create(targetUrl ? { url: targetUrl } : {});
      
      if (targetUrl) {
        await new Promise(resolve => {
          const listener = (tabId, info) => {
            if (tabId === newTab.id && info.status === 'complete') {
              chrome.tabs.onUpdated.removeListener(listener);
              resolve();
            }
          };
          chrome.tabs.onUpdated.addListener(listener);
          setTimeout(() => {
            chrome.tabs.onUpdated.removeListener(listener);
            resolve();
          }, 12000);
        });
      }
      
      await updateActiveTab();
      result = { success: true, data: { tab_opened: true, url: targetUrl || 'new tab' } };
    } else if (originalAction === 'search_web_background') {
      let searchSuccess = false;
      let resultsText = '';
      
      // 1. Google CSE
      if (!searchSuccess && standaloneSettings.googleApiKey && standaloneSettings.googleCseId) {
        try {
          const response = await fetch(`https://customsearch.googleapis.com/customsearch/v1?cx=${standaloneSettings.googleCseId}&q=${encodeURIComponent(msg.query)}&key=${standaloneSettings.googleApiKey}`);
          if (!response.ok) throw new Error(`Google API Error: ${response.status}`);
          const data = await response.json();
          if (data.items) {
             resultsText = data.items.slice(0, 3).map(r => `Title: ${r.title}\nSnippet: ${r.snippet}\nLink: ${r.link}`).join('\n\n');
          }
          searchSuccess = true;
          handleMessage({ action: 'action_start', text: `Used Google Search for: ${msg.query}` });
        } catch (e) {
          console.warn('Google CSE failed, falling back...', e);
        }
      }

      // 2. Tavily
      if (!searchSuccess && standaloneSettings.tavilyApiKey) {
        try {
          const response = await fetch('https://api.tavily.com/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              api_key: standaloneSettings.tavilyApiKey,
              query: msg.query,
              search_depth: 'basic',
              include_answer: true,
              max_results: 3
            })
          });
          if (!response.ok) throw new Error(`Tavily API Error: ${response.status}`);
          const data = await response.json();
          resultsText = data.answer ? `Tavily Answer: ${data.answer}\n\n` : '';
          if (data.results) {
             resultsText += data.results.map(r => `Title: ${r.title}\nSnippet: ${r.content}`).join('\n\n');
          }
          searchSuccess = true;
          handleMessage({ action: 'action_start', text: `Used Tavily Search for: ${msg.query}` });
        } catch (e) {
          console.warn('Tavily failed, falling back...', e);
        }
      }

      // 3. DuckDuckGo (Fallback)
      if (!searchSuccess) {
        const response = await fetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(msg.query)}`);
        if (!response.ok) throw new Error(`DuckDuckGo Error: ${response.status}`);
        const text = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(text, 'text/html');
        resultsText = Array.from(doc.querySelectorAll('.result')).slice(0, 3).map(el => {
          const title = el.querySelector('.result__title')?.textContent?.trim() || '';
          const snippet = el.querySelector('.result__snippet')?.textContent?.trim() || '';
          return `Title: ${title}\nSnippet: ${snippet}`;
        }).join('\n\n');
        searchSuccess = true;
        handleMessage({ action: 'action_start', text: `Used DuckDuckGo Search for: ${msg.query}` });
      }

      result = { success: true, data: { search_results: resultsText || "No results found." } };
    } else if (originalAction === 'screenshot') {
      const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 60 });
      result = { success: true, data: { screenshot_taken: true, dataUrl: dataUrl } };
    } else if (originalAction === 'download_notes') {
      const blob = new Blob([msg.content], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = msg.filename || 'class_notes.html';
      a.click();
      URL.revokeObjectURL(url);
      result = { success: true, data: { downloaded: a.download } };
    } else {
      // Send to content script
      const { action, ...data } = msg;
      
      const sendMessageWithRetry = async (retryCount = 3) => {
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId: currentTab.id, allFrames: true },
            func: async (a, d) => {
              if (typeof window.louisProcessAction === 'function') {
                return await window.louisProcessAction(a, d);
              }
              return { success: false, error: 'louisProcessAction not found' };
            },
            args: [action, data]
          });
          
          if (!results || results.length === 0) {
            return { success: false, error: 'No response from any frame' };
          }
          
          // Check if any frame succeeded (crucial for iframes)
          const successfulFrame = results.find(r => r.result && r.result.success);
          if (successfulFrame) {
            return successfulFrame.result;
          }
          
          // If all failed because content.js is not injected
          const notInjected = results.every(r => r.result && r.result.error === 'louisProcessAction not found');
          if (notInjected && retryCount > 0) {
            await chrome.scripting.executeScript({
              target: { tabId: currentTab.id, allFrames: true },
              files: ['content.js']
            });
            await new Promise(r => setTimeout(r, 500));
            return await sendMessageWithRetry(retryCount - 1);
          }
          
          // Otherwise return the first frame's error (usually top frame)
          return results[0].result || { success: false, error: 'Action failed in all frames' };
          
        } catch (err) {
          if (retryCount > 0) {
            try {
              await chrome.scripting.executeScript({
                target: { tabId: currentTab.id, allFrames: true },
                files: ['content.js']
              });
              await new Promise(r => setTimeout(r, 500));
              return await sendMessageWithRetry(retryCount - 1);
            } catch (injErr) {
              return { success: false, error: `Could not inject script: ${injErr.message}. Please hard refresh the page.` };
            }
          }
          return { success: false, error: err.message };
        }
      };
      
      result = await sendMessageWithRetry(3);
    }
  } catch (e) {
    result = { success: false, error: e.toString() };
  }

  return result;
}

// ── UI Updates ─────────────────────────────────────────────────────────────

let currentTypingEl = null;

function appendMessage(role, text) {
  removeTypingIndicator();
  
  const msgEl = document.createElement('div');
  msgEl.className = `msg ${role}-msg`;
  
  const avatar = document.createElement('div');
  avatar.className = `msg-avatar ${role}`;
  avatar.innerHTML = role === 'user'
    ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M8 4v14a2 2 0 002 2h6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  
  const body = document.createElement('div');
  body.className = 'msg-body';
  
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  if (role === 'ai' && text.startsWith('Standalone Error:')) {
    msgEl.classList.add('error-msg');
  }
  
  // Basic markdown parsing for links and code
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') // escape HTML
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>')
    .replace(/\n/g, '<br>');
    
  bubble.innerHTML = html;
  
  body.appendChild(bubble);
  msgEl.appendChild(avatar);
  msgEl.appendChild(body);
  
  els.chat.appendChild(msgEl);
  scrollToBottom();
}

function appendActionLog(status, text) {
  removeTypingIndicator();
  
  // Check if the last child is an action group
  const lastChild = els.chat.lastElementChild;
  let actionGroup;
  let details;
  
  if (lastChild && lastChild.classList.contains('action-group')) {
    actionGroup = lastChild;
    details = actionGroup.querySelector('details');
  } else {
    // Create new action group
    actionGroup = document.createElement('div');
    actionGroup.className = 'msg action-group';
    
    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar action';
    avatar.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>';
    
    const body = document.createElement('div');
    body.className = 'msg-body';
    
    details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.innerHTML = '<span class="summary-text">System Process</span><svg class="summary-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>';
    
    details.appendChild(summary);
    body.appendChild(details);
    
    actionGroup.appendChild(avatar);
    actionGroup.appendChild(body);
    els.chat.appendChild(actionGroup);
  }
  
  // Create the individual action line
  const actionLine = document.createElement('div');
  actionLine.className = 'action-line';
  if (status === 'error') actionLine.classList.add('error-line');
  
  const dot = document.createElement('div');
  dot.className = `action-dot ${status}`;
  
  const span = document.createElement('span');
  
  if (text.endsWith('...')) {
    const baseText = text.slice(0, -3);
    const sanitizedBase = baseText.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    span.innerHTML = `${sanitizedBase}<span class="bouncing-text-dots"><span>.</span><span>.</span><span>.</span></span>`;
  } else {
    span.textContent = text;
  }
  
  actionLine.appendChild(dot);
  actionLine.appendChild(span);
  
  // Append to the details block
  details.appendChild(actionLine);
  
  // Automatically open the details while it's loading, or keep it open if it's the latest
  details.open = true;
  
  scrollToBottom();
}

function showTypingIndicator(modelName = '') {
  removeTypingIndicator();
  
  const msgEl = document.createElement('div');
  msgEl.className = 'msg ai-msg typing-msg';
  
  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar ai';
  avatar.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M8 4v14a2 2 0 002 2h6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  
  const body = document.createElement('div');
  body.className = 'msg-body';
  
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble typing';
  
  let labelHtml = '';
  if (modelName) {
    labelHtml = `<div style="font-size: 10px; color: var(--accent-color); margin-bottom: 6px; font-weight: 500; opacity: 0.8; text-transform: uppercase; letter-spacing: 0.5px;">${modelName}</div>`;
  }
  
  bubble.innerHTML = `${labelHtml}<div style="display: flex; gap: 4px;"><span></span><span></span><span></span></div>`;
  
  body.appendChild(bubble);
  msgEl.appendChild(avatar);
  msgEl.appendChild(body);
  
  els.chat.appendChild(msgEl);
  currentTypingEl = msgEl;
  scrollToBottom();
}

function removeTypingIndicator() {
  if (currentTypingEl) {
    currentTypingEl.remove();
    currentTypingEl = null;
  }
}

function scrollToBottom() {
  els.chat.scrollTop = els.chat.scrollHeight;
}

function showToast(msg, type = 'ok') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  
  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ── Input Handling & Uploads ───────────────────────────────────────────────

let messageHistory = [];
let historyIndex = 0;
let draftMessage = '';
let currentAttachment = null;
let savedChatHistory = [];

function clearAttachment() {
  currentAttachment = null;
  els.fileUpload.value = '';
  els.attachmentPreview.classList.add('hidden');
}

function loadChatHistory() {
  chrome.storage.local.get(['chatHistory'], (result) => {
    if (result.chatHistory) {
      savedChatHistory = result.chatHistory;
    }
  });
}

function saveChatHistory(text) {
  savedChatHistory.push(text);
  if (savedChatHistory.length > 50) savedChatHistory.shift();
  chrome.storage.local.set({ chatHistory: savedChatHistory });
}

function sendMessage(text) {
  if (!text.trim() && !currentAttachment) return;
  
  if (text.trim() === '/recent') {
    els.chat.innerHTML = '';
    const recentDiv = document.createElement('div');
    recentDiv.className = 'welcome';
    recentDiv.innerHTML = '<h2 class="welcome-title">Recent History</h2><div class="quick-actions" id="recent-actions"></div>';
    els.chat.appendChild(recentDiv);
    const actionsContainer = document.getElementById('recent-actions');
    [...savedChatHistory].reverse().slice(0, 10).forEach(pastMsg => {
      const btn = document.createElement('button');
      btn.className = 'quick-btn';
      btn.textContent = pastMsg.length > 40 ? pastMsg.substring(0, 40) + '...' : pastMsg;
      btn.onclick = () => { els.input.value = pastMsg; els.input.focus(); };
      actionsContainer.appendChild(btn);
    });
    els.input.value = '';
    return;
  }

  const trimmed = text.trim();
  if (trimmed && messageHistory[messageHistory.length - 1] !== trimmed) {
    messageHistory.push(trimmed);
  }
  historyIndex = messageHistory.length;
  draftMessage = '';
  
  if (trimmed) saveChatHistory(trimmed);
  
  let userText = trimmed;
  let attachedData = null;

  if (currentAttachment) {
    if (currentAttachment.type === 'image') {
      attachedData = currentAttachment.content;
      userText = `[Attached image: ${currentAttachment.name}]\n${userText}`;
    } else {
      userText = `[Attached file: ${currentAttachment.name}]\n\n<file_content>\n${currentAttachment.content}\n</file_content>\n\n${userText}`;
    }
  }
  
  appendMessage('user', userText);
  showTypingIndicator();
  
  els.input.value = '';
  els.input.style.height = 'auto';
  checkInput();

  // Always use the standalone extension logic for chat
  currentAbortController = new AbortController();
  els.sendBtn.classList.add('hidden');
  els.stopBtn.classList.remove('hidden');
  processStandaloneMessage(userText, attachedData);
  
  clearAttachment();
  checkInput();
}

function checkInput() {
  const hasText = els.input.value.trim().length > 0 || currentAttachment;
  els.sendBtn.disabled = !hasText;
}

// ── Standalone Agent (Ollama / Cloud) ────────────────────────────────────

function classifyTask(text) {
  if (!text) return currentStandaloneModelRole;
  const COMPLEX_KEYWORDS = /\b(code|script|python|bash|git|html|css|js|javascript|json|yaml|bug|fix|refactor|error|debug|implement|plan|architect|design|structure|framework|database|schema|api|backend|frontend|click|scroll|type|read|screenshot|navigate|find|search|summarize|analyze)\b/i;
  return COMPLEX_KEYWORDS.test(text) ? 'smart' : 'fast';
}

function extractToolJSON(text) {
  const regex = /```(?:json)?\s*(\{[\s\S]*?\})\s*```/;
  const match = text.match(regex);
  if (match) {
    try {
      const parsed = JSON.parse(match[1]);
      return { toolData: parsed, matchText: match[0] };
    } catch(e) {}
  }
  
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start !== -1 && end !== -1 && end > start) {
    try {
      const block = text.substring(start, end + 1);
      const parsed = JSON.parse(block);
      if (parsed.tool || parsed.action) {
        return { toolData: parsed, matchText: block };
      }
    } catch(e) {}
  }
  return null;
}

async function processStandaloneMessage(text, attachedData = null) {
  if (standaloneMessages.length === 0) {
    standaloneMessages.push({ role: 'system', content: STANDALONE_SYSTEM_PROMPT });
  }

  if (text) {
    let promptText = text;
    if (currentTab) {
      promptText = `Current tab: ${currentTab.title} (${currentTab.url})\n\nUser: ${text}`;
    }
    
    if (attachedData) {
      standaloneMessages.push({
        role: 'user',
        content: [
          { type: 'text', text: promptText },
          { type: 'image_url', image_url: { url: attachedData } }
        ]
      });
    } else {
      standaloneMessages.push({ role: 'user', content: promptText });
    }
    
    // Classify and select model
    currentStandaloneModelRole = classifyTask(text);
    const modelName = currentStandaloneModelRole === 'smart' ? standaloneSettings.smartModel : standaloneSettings.fastModel;
    showTypingIndicator(modelName);
  }

  const activeModel = currentStandaloneModelRole === 'smart' ? standaloneSettings.smartModel : standaloneSettings.fastModel;

  const FALLBACK_MODELS = {
    openrouter: {
      smart: [
        'qwen/qwen3-coder:free',
        'openai/gpt-oss-120b:free',
        'cohere/north-mini-code:free',
        'poolside/laguna-m.1:free',
        'nvidia/nemotron-3-ultra-550b-a55b:free'
      ],
      fast: [
        'google/gemma-4-31b-it:free',
        'meta-llama/llama-3.3-70b-instruct:free',
        'nousresearch/hermes-3-llama-3.1-405b:free',
        'qwen/qwen3-coder:free'
      ]
    },
    ollama: {
      smart: [
        'qwen3-coder:480b',
        'qwen3-coder:30b',
        'devstral-2:123b'
      ],
      fast: [
        'gemma4:31b',
        'gemma3:27b',
        'deepseek-v4-flash'
      ]
    },
    openai: {
      smart: [
        'gpt-4o',
        'o1-mini'
      ],
      fast: [
        'gpt-4o-mini',
        'gpt-3.5-turbo'
      ]
    }
  };

  window._dynOr = window._dynOr || [];
  window._dynOl = window._dynOl || [];

  if (!window._dynamicModelsFetched) {
    window._dynamicModelsFetched = true;
    try {
      fetch('https://openrouter.ai/api/v1/models').then(r => r.json()).then(data => {
        window._dynOr = data.data.filter(m => {
          let p = m.pricing.prompt; let c = m.pricing.completion;
          return (parseFloat(p) === 0 && parseFloat(c) === 0) || (p === "0" && c === "0");
        }).map(m => m.id);
      }).catch(e=>{});
      const olUrl = (standaloneSettings.baseUrl || 'http://localhost:11434').replace(/\/$/, '') + '/api/tags';
      fetch(olUrl).then(r => r.json()).then(data => {
        window._dynOl = data.models.map(m => m.name);
      }).catch(e=>{});
    } catch(e) {}
  }

  FALLBACK_MODELS.openrouter.smart.push(...window._dynOr);
  FALLBACK_MODELS.openrouter.fast.push(...window._dynOr);
  FALLBACK_MODELS.ollama.smart.push(...window._dynOl);
  FALLBACK_MODELS.ollama.fast.push(...window._dynOl);

  const PROVIDER_ORDER = ['openrouter', 'ollama', 'openai'];

  window.activeKeyIndexes = window.activeKeyIndexes || {};

  async function executeOllamaOrCloudFetch(originalBody, p = standaloneSettings.provider, modelOverride = null, keyIndex = null) {
    if (keyIndex === null) {
      keyIndex = window.activeKeyIndexes[p] || 0;
    }
    
    let headers = { 'Content-Type': 'application/json' };
    
    const providerKeysRaw = standaloneSettings.keys[p] || '';
    const keyArray = providerKeysRaw.split(',').map(k => k.trim()).filter(k => k.length > 5);

    let endpoint = 'http://localhost:11434/api/chat';
    if (standaloneSettings.baseUrl) {
      // NOTE: Ollama hosts an official Cloud API (e.g. ollama.com). Users also map generic Cloud APIs
      // (like DeepSeek, Zhipu, Together) under the 'ollama' provider setting.
      // If the URL contains /v1 or they provided keys, it is treated as a standard OpenAI-compatible Cloud API
      // rather than a local Ollama instance, avoiding local-only formatting bugs.
      let base = standaloneSettings.baseUrl.replace(/\/$/, '');
      if (base.endsWith('/chat/completions') || base.endsWith('/api/chat')) {
        endpoint = base;
      } else if (base.includes('/v1') || keyArray.length > 0) {
        endpoint = `${base}/v1/chat/completions`;
      } else {
        endpoint = `${base}/api/chat`;
      }
    }
    
    const AVAILABLE_PROVIDERS = PROVIDER_ORDER.filter(provider => {
      if (provider === 'ollama') return true;
      const keysRaw = standaloneSettings.keys[provider] || '';
      return keysRaw.split(',').some(k => k.trim().length > 5);
    });

    if (keyArray.length === 0 && !['ollama'].includes(p)) {
      if (AVAILABLE_PROVIDERS.length > 0) {
        const nextProvider = AVAILABLE_PROVIDERS[0];
        handleMessage({ action: 'action_start', text: `[${p}] No API keys configured. Switching to ${nextProvider}...` });
        return await executeOllamaOrCloudFetch(originalBody, nextProvider, null, 0);
      }
      throw new Error(`No API keys configured for ${p}`);
    }

    const apiKeyToUse = keyArray.length > 0 ? keyArray[Math.min(keyIndex, keyArray.length - 1)] : '';

    let activeModel = modelOverride || (currentStandaloneModelRole === 'smart' ? standaloneSettings.smartModel : standaloneSettings.fastModel);

    // If we've switched provider and have no modelOverride, use the default models for that provider
    if (p !== standaloneSettings.provider && !modelOverride) {
       activeModel = currentStandaloneModelRole === 'smart' ? DEFAULT_MODELS[p].smart : DEFAULT_MODELS[p].fast;
    }

    if (p === 'openrouter') {
      endpoint = 'https://openrouter.ai/api/v1/chat/completions';
      if (apiKeyToUse) headers['Authorization'] = `Bearer ${apiKeyToUse}`;
    } else if (p === 'openai') {
      endpoint = 'https://api.openai.com/v1/chat/completions';
      if (apiKeyToUse) headers['Authorization'] = `Bearer ${apiKeyToUse}`;
    } else if (p === 'ollama') {
      if (apiKeyToUse) headers['Authorization'] = `Bearer ${apiKeyToUse}`;
    }

    // Deep copy messages to allow API-specific formatting without corrupting history
    const body = { ...originalBody, model: activeModel, messages: JSON.parse(JSON.stringify(originalBody.messages)) };

    // Format vision payload for Ollama
    if (p === 'ollama' && endpoint.endsWith('/api/chat')) {
      body.messages.forEach(m => {
        if (Array.isArray(m.content)) {
          let textPart = m.content.find(c => c.type === 'text');
          let imgPart = m.content.find(c => c.type === 'image_url');
          m.content = textPart ? textPart.text : '';
          if (imgPart) {
            m.images = m.images || [];
            m.images.push(imgPart.image_url.url.split(',')[1]);
          }
        }
      });
    }

    // ── Smart retry + cascade logic ──────────────────────────────────────
    let res;
    try {
      const fetchOptions = {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(body)
      };
      if (currentAbortController) {
        fetchOptions.signal = currentAbortController.signal;
      }
      res = await fetch(endpoint, fetchOptions);
    } catch(err) {
      if (err.name === 'AbortError') throw err;
      res = { ok: false, status: 0, statusText: err.message || 'Network Failure' };
    }

    if (res.ok) return await res.json();

    const isModelError = res.status === 400 || res.status === 404 || res.status === 500 || res.status === 502 || res.status === 503;
    const isKeyError = res.status === 401 || res.status === 403 || res.status === 402 || res.status === 429;

    if (isModelError) {
      const fallbackList = (FALLBACK_MODELS[p] && FALLBACK_MODELS[p][currentStandaloneModelRole]) || [];
      const idx = fallbackList.indexOf(activeModel);
      
      let nextModel = null;
      if (idx !== -1 && idx + 1 < fallbackList.length) {
        nextModel = fallbackList[idx + 1];
      } else if (idx === -1 && fallbackList.length > 0 && activeModel !== fallbackList[0]) {
        nextModel = fallbackList[0];
      }

      if (nextModel) {
        if (currentStandaloneModelRole === 'smart') {
          standaloneSettings.smartModel = nextModel;
          document.getElementById('api-smart-model').value = nextModel;
        } else {
          standaloneSettings.fastModel = nextModel;
          document.getElementById('api-fast-model').value = nextModel;
        }
        showTypingIndicator(nextModel);
        
        return await executeOllamaOrCloudFetch(originalBody, p, nextModel, keyIndex);
      }
    } else if (isKeyError) {
      if (keyIndex + 1 < keyArray.length) {
        window.activeKeyIndexes[p] = keyIndex + 1;
        return await executeOllamaOrCloudFetch(originalBody, p, activeModel, keyIndex + 1);
      }
    }

    // ── All keys or models exhausted for current provider → try next provider ──
    const currentProviderIndex = AVAILABLE_PROVIDERS.indexOf(p);
    if (currentProviderIndex !== -1 && currentProviderIndex + 1 < AVAILABLE_PROVIDERS.length) {
      const nextProvider = AVAILABLE_PROVIDERS[currentProviderIndex + 1];
      handleMessage({ action: 'action_start', text: `[${p}] Exhausted. Hard failing over to ${nextProvider}...` });
      
      // Persist provider switch for the session
      standaloneSettings.provider = nextProvider;
      
      const nextModel = currentStandaloneModelRole === 'smart' ? DEFAULT_MODELS[nextProvider].smart : DEFAULT_MODELS[nextProvider].fast;
      if (currentStandaloneModelRole === 'smart') {
        standaloneSettings.smartModel = nextModel;
        document.getElementById('api-smart-model').value = nextModel;
      } else {
        standaloneSettings.fastModel = nextModel;
        document.getElementById('api-fast-model').value = nextModel;
      }
      showTypingIndicator(nextModel);
      
      return await executeOllamaOrCloudFetch(originalBody, nextProvider, null, 0);
    }

    // ── Everything failed ──
    throw new Error(`All providers exhausted. Last: ${p} error ${res.status} ${res.statusText}`);
  }

  try {
    let body = {
      messages: standaloneMessages,
      stream: false
    };

    const data = await executeOllamaOrCloudFetch(body);

    let assistantContent = '';
    if (data.choices && data.choices.length > 0 && data.choices[0].message) {
      assistantContent = data.choices[0].message.content;
    } else if (data.message && typeof data.message.content === 'string') {
      assistantContent = data.message.content;
    } else if (data.error) {
      throw new Error(typeof data.error === 'string' ? data.error : (data.error.message || JSON.stringify(data.error)));
    } else {
      throw new Error("Unexpected API response: " + JSON.stringify(data).substring(0, 100));
    }
    standaloneMessages.push({ role: 'assistant', content: assistantContent });

    // Look for tool calls
    const extraction = extractToolJSON(assistantContent);

    if (extraction) {
      const toolData = extraction.toolData;
      const tool = toolData.tool || toolData.action; // Some models use 'action'
      const args = toolData.arguments || toolData.args || {};
      
      const actionPayload = { action: tool, ...args };
      
      handleMessage({ action: 'action_start', text: `Executing: ${tool}...` });
      
      const timeoutPromise = new Promise(resolve => setTimeout(() => resolve({ success: false, error: 'Tool execution timed out after 15 seconds' }), 15000));
      const result = await Promise.race([
        executeBrowserActionLocally(actionPayload),
        timeoutPromise
      ]);
      
      if (result.success) {
        handleMessage({ action: 'action_complete', text: `✓ ${tool} — done` });
      } else {
        handleMessage({ action: 'action_error', text: `✗ ${tool}: ${result.error}` });
      }

      if (tool === 'screenshot' && result.success && result.data.dataUrl) {
         const cleanResult = JSON.parse(JSON.stringify(result));
         cleanResult.data.dataUrl = "<base64 attached as image_url>";
         
         standaloneMessages.push({ 
           role: 'user', 
           content: [
             { type: "text", text: `Tool Result:\n\`\`\`json\n${JSON.stringify(cleanResult, null, 2)}\n\`\`\`` },
             { type: "image_url", image_url: { url: result.data.dataUrl } }
           ]
         });
      } else {
         standaloneMessages.push({ role: 'user', content: `Tool Result:\n\`\`\`json\n${JSON.stringify(result, null, 2)}\n\`\`\`` });
      }
      
      const currentActiveModel = currentStandaloneModelRole === 'smart' ? standaloneSettings.smartModel : standaloneSettings.fastModel;
      showTypingIndicator(currentActiveModel);
      processStandaloneMessage(null); // Recursively call with no new text to continue
      return;
    }

    // Display text
    const displayText = extraction ? assistantContent.replace(extraction.matchText, '').trim() : assistantContent.trim();
    if (displayText) {
      handleMessage({ action: 'response', text: displayText });
    } else {
      // Just in case it returned empty
      handleMessage({ action: 'response', text: '' });
    }

  } catch (err) {
    if (err.name === 'AbortError') {
      handleMessage({ action: 'action_error', text: 'Generation stopped by user.' });
    } else {
      let errorMsg = `API Error: ${err.message}`;
      if (err.message.includes('Failed to fetch') && standaloneSettings.provider === 'ollama') {
         errorMsg = `Connection failed. Make sure your Ollama Base URL (${standaloneSettings.baseUrl}) is correct and running.`;
      }
      handleMessage({ action: 'action_error', text: `Standalone Error: ${errorMsg}` });
    }
    handleMessage({ action: 'response', text: '' }); // clear typing indicator
  } finally {
    els.sendBtn.classList.remove('hidden');
    els.stopBtn.classList.add('hidden');
  }
}

// ── Initialization ─────────────────────────────────────────────────────────

function initUI() {
  updateActiveTab();
  connect();
  checkInput();

  // Auto-resize textarea
  els.input.addEventListener('input', () => {
    els.input.style.height = 'auto';
    els.input.style.height = Math.min(els.input.scrollHeight, 140) + 'px';
    checkInput();
  });

  els.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(els.input.value);
    } else if (e.key === 'ArrowUp') {
      if (historyIndex > 0) {
        e.preventDefault();
        if (historyIndex === messageHistory.length) {
          draftMessage = els.input.value;
        }
        historyIndex--;
        els.input.value = messageHistory[historyIndex];
        setTimeout(() => els.input.selectionStart = els.input.selectionEnd = els.input.value.length, 0);
      }
    } else if (e.key === 'ArrowDown') {
      if (historyIndex < messageHistory.length) {
        e.preventDefault();
        historyIndex++;
        if (historyIndex === messageHistory.length) {
          els.input.value = draftMessage;
        } else {
          els.input.value = messageHistory[historyIndex];
        }
        setTimeout(() => els.input.selectionStart = els.input.selectionEnd = els.input.value.length, 0);
      }
    }
  });

  els.input.addEventListener('paste', (e) => {
    const items = (e.clipboardData || window.clipboardData).items;
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (!file) continue;
        const reader = new FileReader();
        reader.onload = (ev) => {
          currentAttachment = { type: 'image', content: ev.target.result, name: file.name || 'pasted-image.png' };
          els.attachmentName.textContent = file.name || 'pasted-image.png';
          els.attachmentPreview.classList.remove('hidden');
          checkInput();
        };
        reader.readAsDataURL(file);
        break;
      }
    }
  });

  els.uploadBtn.addEventListener('click', () => els.fileUpload.click());

  els.attachmentRemove.addEventListener('click', () => {
    clearAttachment();
    checkInput();
  });

  els.fileUpload.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    els.attachmentName.textContent = file.name;
    els.attachmentPreview.classList.remove('hidden');

    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        currentAttachment = { type: 'image', content: ev.target.result, name: file.name };
        checkInput();
      };
      reader.readAsDataURL(file);
    } else if (file.type === 'application/pdf') {
      try {
        const reader = new FileReader();
        reader.onload = async (ev) => {
          const typedarray = new Uint8Array(ev.target.result);
          const pdf = await pdfjsLib.getDocument(typedarray).promise;
          let fullText = '';
          for (let i = 1; i <= pdf.numPages; i++) {
            const page = await pdf.getPage(i);
            const textContent = await page.getTextContent();
            const pageText = textContent.items.map(item => item.str).join(' ');
            fullText += `--- Page ${i} ---\n${pageText}\n\n`;
          }
          currentAttachment = { type: 'text', content: fullText, name: file.name };
          checkInput();
        };
        reader.readAsArrayBuffer(file);
      } catch (err) {
        console.error('PDF parsing error', err);
        currentAttachment = { type: 'text', content: '[Error parsing PDF: ' + err.message + ']', name: file.name };
        checkInput();
      }
    } else {
      const reader = new FileReader();
      reader.onload = (ev) => {
        currentAttachment = { type: 'text', content: ev.target.result, name: file.name };
        checkInput();
      };
      reader.readAsText(file);
    }
  });

  // Load Settings
  chrome.storage.local.get(['louisSettings'], (result) => {
    if (result.louisSettings) {
      // Migration: flat structure to keys object
      if (result.louisSettings.apiKey !== undefined && !result.louisSettings.keys) {
        result.louisSettings.keys = {
          openrouter: '',
          openai: '',
          ollama: ''
        };
        if (result.louisSettings.provider) {
          const pk = result.louisSettings.apiKey || '';
          const bk = result.louisSettings.backupApiKey || '';
          result.louisSettings.keys[result.louisSettings.provider] = [pk, bk].filter(x => x).join(',');
        }
        delete result.louisSettings.apiKey;
        delete result.louisSettings.backupApiKey;
      }
      
      // Migration: convert nested object keys to comma-separated string
      if (result.louisSettings.keys) {
        for (const [p, kObj] of Object.entries(result.louisSettings.keys)) {
          if (kObj && typeof kObj === 'object' && !Array.isArray(kObj)) {
             result.louisSettings.keys[p] = [kObj.primary, kObj.backup].filter(x => x).join(',');
          }
        }
      }
      
      // Removed broken migration for localhost url
      
      standaloneSettings = { ...standaloneSettings, ...result.louisSettings };
    }
    
    // Set UI elements
    document.getElementById('api-fast-model').value = standaloneSettings.fastModel;
    document.getElementById('api-smart-model').value = standaloneSettings.smartModel;
    document.getElementById('api-base-url').value = standaloneSettings.baseUrl || 'http://localhost:11434';
    document.getElementById('tavily-api-key').value = standaloneSettings.tavilyApiKey || '';
    document.getElementById('google-api-key').value = standaloneSettings.googleApiKey || '';
    document.getElementById('google-cse-id').value = standaloneSettings.googleCseId || '';
    
    document.getElementById('openrouter-keys').value = standaloneSettings.keys['openrouter'] || '';
    document.getElementById('ollama-keys').value = standaloneSettings.keys['ollama'] || '';
    
    updateSettingsUI();
  });

  // DEFAULT_MODELS is now defined at module scope (top of file)

  // Settings Modal Handlers
  const settingsBtn = document.getElementById('settings-btn');
  const settingsModal = document.getElementById('settings-modal');
  const settingsClose = document.getElementById('settings-close');
  const settingsSave = document.getElementById('settings-save');
  const fastModelInput = document.getElementById('api-fast-model');
  const smartModelInput = document.getElementById('api-smart-model');

  settingsBtn.addEventListener('click', () => settingsModal.classList.add('show'));
  settingsClose.addEventListener('click', () => settingsModal.classList.remove('show'));
  
  function updateSettingsUI() {
    // If no custom model is typed, display the default openrouter models as hints
    fastModelInput.placeholder = `e.g. ${DEFAULT_MODELS.openrouter.fast}`;
    smartModelInput.placeholder = `e.g. ${DEFAULT_MODELS.openrouter.smart}`;
  }

  function saveSettingsToStorage() {
    standaloneSettings.fastModel = document.getElementById('api-fast-model').value;
    standaloneSettings.smartModel = document.getElementById('api-smart-model').value;
    standaloneSettings.baseUrl = document.getElementById('api-base-url').value;
    standaloneSettings.tavilyApiKey = document.getElementById('tavily-api-key').value;
    standaloneSettings.googleApiKey = document.getElementById('google-api-key').value;
    standaloneSettings.googleCseId = document.getElementById('google-cse-id').value;
    
    const orKeys = document.getElementById('openrouter-keys').value;
    const olKeys = document.getElementById('ollama-keys').value;
    
    standaloneSettings.keys['openrouter'] = orKeys;
    standaloneSettings.keys['ollama'] = olKeys;
    
    // Auto-select starting provider
    if (orKeys && orKeys.length > 5) {
      standaloneSettings.provider = 'openrouter';
    } else if (olKeys && olKeys.length > 5) {
      standaloneSettings.provider = 'ollama';
    } else {
      standaloneSettings.provider = 'openrouter';
    }
    
    chrome.storage.local.set({ louisSettings: standaloneSettings });
  }

  // Auto-save whenever inputs lose focus or change
  document.getElementById('openrouter-keys').addEventListener('blur', saveSettingsToStorage);
  document.getElementById('ollama-keys').addEventListener('blur', saveSettingsToStorage);
  document.getElementById('api-base-url').addEventListener('blur', saveSettingsToStorage);
  document.getElementById('api-fast-model').addEventListener('blur', saveSettingsToStorage);
  document.getElementById('api-smart-model').addEventListener('blur', saveSettingsToStorage);
  document.getElementById('tavily-api-key').addEventListener('blur', saveSettingsToStorage);
  document.getElementById('google-api-key').addEventListener('blur', saveSettingsToStorage);
  document.getElementById('google-cse-id').addEventListener('blur', saveSettingsToStorage);

  settingsSave.addEventListener('click', () => {
    saveSettingsToStorage();
    settingsModal.classList.remove('show');
    showToast('Settings saved!');
  });

  els.sendBtn.addEventListener('click', () => {
    sendMessage(els.input.value);
  });

  els.stopBtn.addEventListener('click', () => {
    if (currentAbortController) {
      currentAbortController.abort();
      currentAbortController = null;
    }
  });

  // Quick Action Buttons
  document.querySelectorAll('.quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      sendMessage(btn.dataset.prompt);
    });
  });

  // Keep connection alive
  setInterval(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: 'ping' }));
    }
  }, 15000);
}
