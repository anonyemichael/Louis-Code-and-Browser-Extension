/**
 * Louis Web Agent — Content Script
 * 
 * Injected into every web page. Handles DOM interaction commands:
 *   - read_page:    Extract visible text, links, buttons, inputs
 *   - click:        Click an element by selector, text, or role
 *   - type:         Type text into an input field
 *   - scroll:       Scroll the page or to a specific element
 *   - get_elements: Build a queryable map of interactive elements
 *   - fill_form:    Auto-fill form fields by label matching
 *   - wait:         Wait for an element to appear
 * 
 * Communicates with background.js via chrome.runtime messaging.
 */

(() => {
  'use strict';

  // ── Utility: Deep Selector (pierces Shadow DOM and Iframes) ──────────────
  function queryDeep(selector, root = document) {
    // Standard query
    let result = null;
    try {
      result = root.querySelector(selector);
    } catch(e) {}
    if (result) return result;

    // Search inside shadow roots and accessible iframes
    const allNodes = root.querySelectorAll('*');
    for (const node of allNodes) {
      if (node.shadowRoot) {
        const shadowResult = queryDeep(selector, node.shadowRoot);
        if (shadowResult) return shadowResult;
      }
      if (node.tagName === 'IFRAME') {
        try {
          if (node.contentDocument) {
            const iframeResult = queryDeep(selector, node.contentDocument);
            if (iframeResult) return iframeResult;
          }
        } catch(e) {
          // Cross-origin blocked
        }
      }
    }
    return null;
  }

  function queryAllDeep(selector, root = document) {
    let results = [];
    try {
      results = Array.from(root.querySelectorAll(selector));
    } catch(e) {}

    // Search inside shadow roots and accessible iframes
    const allNodes = root.querySelectorAll('*');
    for (const node of allNodes) {
      if (node.shadowRoot) {
        results = results.concat(queryAllDeep(selector, node.shadowRoot));
      }
      if (node.tagName === 'IFRAME') {
        try {
          if (node.contentDocument) {
             results = results.concat(queryAllDeep(selector, node.contentDocument));
          }
        } catch(e) {
          // Cross-origin blocked
        }
      }
    }
    return results;
  }

  // ── Utility: Safe querySelector (wrappers) ──────────────────────────────
  function safeQuery(selector) {
    return queryDeep(selector);
  }

  function safeQueryAll(selector) {
    return queryAllDeep(selector);
  }

  // ── Utility: Get visible text of an element ─────────────────────────────
  function getVisibleText(el) {
    if (!el) return '';
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
      return '';
    }
    return (el.innerText || el.textContent || '').trim();
  }

  // ── Utility: Check if element is visible ────────────────────────────────
  function isVisible(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' &&
           style.visibility !== 'hidden' &&
           parseFloat(style.opacity) > 0;
  }

  // ── Utility: Scroll element into view ───────────────────────────────────
  async function scrollIntoView(el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
    // Wait for smooth scroll to finish so getBoundingClientRect is accurate
    await new Promise(r => setTimeout(r, 500));
  }

  // ── Utility: Fake Mouse Cursor Animation ────────────────────────────────
  let fakeCursor = null;

  function getOrCreateFakeCursor() {
    if (fakeCursor && document.documentElement.contains(fakeCursor)) {
      return fakeCursor;
    }
    
    fakeCursor = document.createElement('div');
    fakeCursor.id = 'louis-fake-cursor';
    // Base64 encoded SVG for a sleek orange cursor with a white border
    fakeCursor.style.cssText = `
      position: fixed;
      top: -100px;
      left: -100px;
      width: 24px;
      height: 24px;
      background-image: url('data:image/svg+xml;utf8,<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 01.35-.15h6.84c.45 0 .67-.54.35-.85L5.5 3.21z" fill="%23da7756" stroke="white" stroke-width="1.5" stroke-linejoin="round"/></svg>');
      background-size: contain;
      background-repeat: no-repeat;
      pointer-events: none;
      z-index: 2147483647;
      transition: top 0.4s cubic-bezier(0.25, 1, 0.5, 1), left 0.4s cubic-bezier(0.25, 1, 0.5, 1), transform 0.1s;
      filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
    `;
    document.documentElement.appendChild(fakeCursor);
    return fakeCursor;
  }

  async function animateCursorTo(x, y) {
    const cursor = getOrCreateFakeCursor();
    
    // If the cursor is off-screen (first use), just teleport it near the center or bottom right first
    // to make the slide-in look natural instead of coming from -100px
    if (parseInt(cursor.style.top) < 0) {
      cursor.style.transition = 'none';
      cursor.style.left = `${window.innerWidth / 2}px`;
      cursor.style.top = `${window.innerHeight}px`;
      // force reflow
      void cursor.offsetWidth;
      cursor.style.transition = 'top 0.4s cubic-bezier(0.25, 1, 0.5, 1), left 0.4s cubic-bezier(0.25, 1, 0.5, 1), transform 0.1s';
    }

    // Move to target
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
    
    // Wait for the movement animation
    await new Promise(r => setTimeout(r, 450));
    
    // Simulate mouse click press down (scale down)
    cursor.style.transform = 'scale(0.8)';
    await new Promise(r => setTimeout(r, 100));
    
    // Simulate mouse click release (scale back)
    cursor.style.transform = 'scale(1)';
    await new Promise(r => setTimeout(r, 100));
  }

  // ── Utility: Simulate human-like events ─────────────────────────────────
  async function simulateClick(el) {
    await scrollIntoView(el);

    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;

    await animateCursorTo(x, y);

    const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
    for (const eventType of events) {
      const event = new MouseEvent(eventType, {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: x,
        clientY: y
      });
      el.dispatchEvent(event);
    }
    
    // Also use native click as a reliable fallback
    try {
      el.click();
    } catch(e) {}
  }

  async function simulateType(el, text, isStealth = false) {
    await scrollIntoView(el);
    
    const rect = el.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    await animateCursorTo(x, y);

    el.focus();

    // Clear existing content
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.value = '';
      el.dispatchEvent(new Event('input', { bubbles: true }));
    } else if (el.isContentEditable) {
      el.innerHTML = '';
    }

    // Type character by character with optional human delay
    for (const char of text) {
      const keyDown = new KeyboardEvent('keydown', { key: char, bubbles: true });
      const keyPress = new KeyboardEvent('keypress', { key: char, bubbles: true });
      const keyUp = new KeyboardEvent('keyup', { key: char, bubbles: true });

      el.dispatchEvent(keyDown);
      el.dispatchEvent(keyPress);

      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        el.value += char;
      } else if (el.isContentEditable) {
        el.innerHTML += char;
      }

      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(keyUp);

      if (isStealth) {
        // Artificial human delay (50ms - 150ms)
        const delay = Math.floor(Math.random() * 100) + 50;
        await new Promise(r => setTimeout(r, delay));
      }
    }

    // Final change event
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // ── Find Element by Multiple Strategies ─────────────────────────────────
  function findElement(params) {
    // Strategy 1: CSS selector
    if (params.selector) {
      const el = safeQuery(params.selector);
      if (el) return el; // For exact selectors, bypass strict visibility checks
    }

    // Strategy 2: Text content match
    if (params.text) {
      const searchText = params.text.toLowerCase().trim();
      const interactiveSelector = 'a, button, [role="button"], input[type="submit"], input[type="button"], label';
      const structuralSelector = 'span, p, h1, h2, h3, h4, h5, h6, li, td, th, div';
      
      const interactiveEls = safeQueryAll(interactiveSelector);
      const structuralEls = safeQueryAll(structuralSelector);

      // Exact match interactive
      for (const el of interactiveEls) {
        if (getVisibleText(el).toLowerCase() === searchText && isVisible(el)) return el;
      }
      // Exact match structural
      for (const el of structuralEls) {
        if (getVisibleText(el).toLowerCase() === searchText && isVisible(el)) return el;
      }
      // Partial match interactive
      for (const el of interactiveEls) {
        if (getVisibleText(el).toLowerCase().includes(searchText) && isVisible(el)) return el;
      }
      // Partial match structural (only if the text is short, to avoid clicking massive wrapper divs)
      for (const el of structuralEls) {
        const text = getVisibleText(el).toLowerCase();
        if (text.includes(searchText) && text.length < 150 && isVisible(el)) return el;
      }
    }

    // Strategy 3: ARIA label
    if (params.label || params.text) {
      const label = (params.label || params.text).toLowerCase();
      const all = safeQueryAll('[aria-label], [title], [placeholder], [alt]');
      for (const el of all) {
        const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
        const title = (el.getAttribute('title') || '').toLowerCase();
        const placeholder = (el.getAttribute('placeholder') || '').toLowerCase();
        const alt = (el.getAttribute('alt') || '').toLowerCase();
        if ((ariaLabel.includes(label) || title.includes(label) ||
             placeholder.includes(label) || alt.includes(label)) && isVisible(el)) {
          return el;
        }
      }
    }

    // Strategy 4: Role
    if (params.role) {
      const els = safeQueryAll(`[role="${params.role}"]`);
      const index = params.index || 0;
      const visible = els.filter(isVisible);
      if (visible[index]) return visible[index];
    }

    // Strategy 5: Nth of type (e.g., "first link", "3rd button")
    if (params.tag && params.index !== undefined) {
      const els = safeQueryAll(params.tag);
      const visible = els.filter(isVisible);
      if (visible[params.index]) return visible[params.index];
    }

    return null;
  }

  // ── Action: Read Page ───────────────────────────────────────────────────
  function actionReadPage() {
    const title = document.title || '';
    const url = window.location.href;

    // Get main body text (cleaned)
    const bodyText = getVisibleText(document.body).substring(0, 8000);

    // Get all links
    const links = safeQueryAll('a[href]')
      .filter(isVisible)
      .slice(0, 30)
      .map((a, i) => ({
        index: i,
        text: getVisibleText(a).substring(0, 100) || '[no text]',
        href: a.href,
      }));

    // Get all buttons
    const buttons = safeQueryAll('button, [role="button"], input[type="submit"], input[type="button"]')
      .filter(isVisible)
      .slice(0, 20)
      .map((btn, i) => ({
        index: i,
        text: getVisibleText(btn).substring(0, 100) || btn.value || '[no text]',
        type: btn.tagName.toLowerCase(),
      }));

    // Get all input fields
    const inputs = safeQueryAll('input, textarea, select, [contenteditable="true"]')
      .filter(el => isVisible(el) && el.type !== 'hidden')
      .slice(0, 20)
      .map((input, i) => ({
        index: i,
        type: input.type || input.tagName.toLowerCase(),
        name: input.name || '',
        placeholder: input.placeholder || '',
        label: findLabelFor(input),
        value: input.value || '',
      }));

    // Get headings
    const headings = safeQueryAll('h1, h2, h3')
      .filter(isVisible)
      .slice(0, 15)
      .map(h => ({
        level: h.tagName.toLowerCase(),
        text: getVisibleText(h).substring(0, 200),
      }));

    return {
      success: true,
      data: {
        title,
        url,
        headings,
        text: bodyText,
        links,
        buttons,
        inputs,
      },
    };
  }

  // ── Helper: Find label for an input ─────────────────────────────────────
  function findLabelFor(input) {
    // Check for associated <label>
    if (input.id) {
      const label = safeQuery(`label[for="${input.id}"]`);
      if (label) return getVisibleText(label).substring(0, 80);
    }

    // Check for wrapping <label>
    const parent = input.closest('label');
    if (parent) {
      const labelText = getVisibleText(parent).replace(input.value || '', '').trim();
      return labelText.substring(0, 80);
    }

    // Check aria-label
    const ariaLabel = input.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel;

    // Check aria-labelledby
    const labelledBy = input.getAttribute('aria-labelledby');
    if (labelledBy) {
      const el = document.getElementById(labelledBy);
      if (el) return getVisibleText(el).substring(0, 80);
    }

    return input.placeholder || input.name || '';
  }

  // ── Action: Click ───────────────────────────────────────────────────────
  async function actionClick(data) {
    const el = findElement(data);
    if (!el) {
      return {
        success: false,
        error: `Could not find element to click. Searched for: ${JSON.stringify(data)}`,
      };
    }

    try {
      // Highlight briefly before clicking
      highlightElement(el);
      await simulateClick(el);

      return {
        success: true,
        data: {
          clicked: getVisibleText(el).substring(0, 100),
          tag: el.tagName.toLowerCase(),
          href: el.href || null,
        },
      };
    } catch (e) {
      return { success: false, error: `Click failed: ${e.message}` };
    }
  }

  // ── Action: Type ────────────────────────────────────────────────────────
  async function actionType(data) {
    const el = findElement(data);
    if (!el) {
      return {
        success: false,
        error: `Could not find input field. Searched for: ${JSON.stringify(data)}`,
      };
    }

    const text = data.text || '';
    const isStealth = data.stealth === true;
    try {
      highlightElement(el);
      await simulateType(el, text, isStealth);

      return {
        success: true,
        data: {
          typed: text,
          field: findLabelFor(el) || el.name || el.placeholder || el.tagName,
        },
      };
    } catch (e) {
      return { success: false, error: `Type failed: ${e.message}` };
    }
  }

  // ── Action: Scroll ──────────────────────────────────────────────────────
  async function actionScroll(data) {
    try {
      if (data.selector || data.text) {
        const el = findElement(data);
        if (el) {
          await scrollIntoView(el);
          return { success: true, data: { scrolledTo: getVisibleText(el).substring(0, 100) } };
        }
        return { success: false, error: 'Element not found for scroll' };
      }

      // Scroll by direction
      const direction = (data.direction || 'down').toLowerCase();
      const amount = data.amount || 500;

      switch (direction) {
        case 'down':
          window.scrollBy({ top: amount, behavior: 'smooth' });
          break;
        case 'up':
          window.scrollBy({ top: -amount, behavior: 'smooth' });
          break;
        case 'top':
          window.scrollTo({ top: 0, behavior: 'smooth' });
          break;
        case 'bottom':
          window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
          break;
      }

      await new Promise(r => setTimeout(r, 500));
      return { success: true, data: { scrolled: direction, amount } };
    } catch (e) {
      return { success: false, error: `Scroll failed: ${e.message}` };
    }
  }

  // ── Action: Get Interactive Elements ────────────────────────────────────
  function actionGetElements(data) {
    const type = (data.element_type || 'all').toLowerCase();
    let elements = [];

    if (type === 'links' || type === 'all') {
      elements = elements.concat(
        safeQueryAll('a[href]').filter(isVisible).slice(0, 25).map((el, i) => ({
          type: 'link',
          index: i,
          text: getVisibleText(el).substring(0, 100),
          href: el.href,
          selector: generateSelector(el),
        }))
      );
    }

    if (type === 'buttons' || type === 'all') {
      elements = elements.concat(
        safeQueryAll('button, [role="button"], input[type="submit"]').filter(isVisible).slice(0, 25).map((el, i) => ({
          type: 'button',
          index: i,
          text: getVisibleText(el).substring(0, 100) || el.value || '',
          selector: generateSelector(el),
        }))
      );
    }

    if (type === 'inputs' || type === 'all') {
      elements = elements.concat(
        safeQueryAll('input, textarea, select').filter(el => isVisible(el) && el.type !== 'hidden').slice(0, 25).map((el, i) => ({
          type: 'input',
          index: i,
          inputType: el.type || 'text',
          name: el.name || '',
          label: findLabelFor(el),
          placeholder: el.placeholder || '',
          value: el.value || '',
          selector: generateSelector(el),
        }))
      );
    }

    return { success: true, data: { elements, count: elements.length } };
  }

  // ── Generate a CSS selector for an element ──────────────────────────────
  function generateSelector(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;

    const tag = el.tagName.toLowerCase();

    // Try name attribute
    if (el.name) return `${tag}[name="${CSS.escape(el.name)}"]`;

    // Try unique class combination
    if (el.className && typeof el.className === 'string') {
      const classes = el.className.trim().split(/\s+/).slice(0, 3);
      if (classes.length > 0 && classes[0]) {
        const selector = `${tag}.${classes.map(c => CSS.escape(c)).join('.')}`;
        const matches = safeQueryAll(selector);
        if (matches.length === 1) return selector;
      }
    }

    // Use nth-child
    const parent = el.parentElement;
    if (parent) {
      const siblings = Array.from(parent.children);
      const index = siblings.indexOf(el) + 1;
      const parentSel = generateSelector(parent);
      return `${parentSel} > ${tag}:nth-child(${index})`;
    }

    return tag;
  }

  // ── Visual Highlight (brief flash on interacted element) ────────────────
  function highlightElement(el) {
    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position: absolute;
      pointer-events: none;
      z-index: 2147483647;
      border: 2px solid #00e5ff;
      background: rgba(0, 229, 255, 0.12);
      border-radius: 4px;
      transition: opacity 0.4s ease;
    `;

    const rect = el.getBoundingClientRect();
    overlay.style.top = (rect.top + window.scrollY - 2) + 'px';
    overlay.style.left = (rect.left + window.scrollX - 2) + 'px';
    overlay.style.width = (rect.width + 4) + 'px';
    overlay.style.height = (rect.height + 4) + 'px';

    document.body.appendChild(overlay);

    setTimeout(() => {
      overlay.style.opacity = '0';
      setTimeout(() => overlay.remove(), 400);
    }, 600);
  }

  // ── Action: Submit (press Enter on focused element or form) ─────────────
  function actionSubmit(data) {
    try {
      // If a specific element is targeted, find it first
      if (data.selector || data.text) {
        const el = findElement(data);
        if (el) {
          if (el.form) {
            el.form.submit();
            return { success: true, data: { submitted: 'form' } };
          }
          // Simulate Enter keypress
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', keyCode: 13, bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', keyCode: 13, bubbles: true }));
          return { success: true, data: { submitted: 'enter_key' } };
        }
      }

      // Try submitting the first visible form
      const forms = safeQueryAll('form');
      for (const form of forms) {
        if (isVisible(form)) {
          form.submit();
          return { success: true, data: { submitted: 'first_form' } };
        }
      }

      return { success: false, error: 'No form or element found to submit' };
    } catch (e) {
      return { success: false, error: `Submit failed: ${e.message}` };
    }
  }

  // ── Action: Live Notes (Caption Scraper) ────────────────────────────────
  let transcript = [];
  let noteInterval = null;
  let isTakingNotes = false;
  let lastCaptionText = "";

  function actionStartNotes() {
    if (isTakingNotes) return { success: false, error: 'Already taking notes' };
    
    transcript = [];
    isTakingNotes = true;
    lastCaptionText = "";
    
    noteInterval = setInterval(() => {
      // Common selectors for Zoom, Google Meet, Teams captions, plus generic aria-live regions
      const capNodes = document.querySelectorAll('.iOzk7, .Mz6pEf, .caption-text, [class*="caption"], [data-tid*="caption"], [aria-live="polite"]');
      let currentCap = "";
      
      capNodes.forEach(n => {
         if (isVisible(n)) {
           currentCap += (n.innerText || n.textContent || '') + "\n";
         }
      });
      
      currentCap = currentCap.trim();
      if (currentCap && currentCap !== lastCaptionText) {
         transcript.push(currentCap);
         lastCaptionText = currentCap;
      }
    }, 2000);
    
    return { success: true, data: { status: 'recording_captions' } };
  }

  function actionStopNotes() {
    if (!isTakingNotes) return { success: false, error: 'Not currently taking notes' };
    
    clearInterval(noteInterval);
    isTakingNotes = false;
    
    // Simple deduplication of identical sequential blocks
    const finalTranscript = transcript.filter((v, i, a) => i === 0 || v !== a[i-1]).join('\n---\n');
    transcript = [];
    return { success: true, data: { transcript: finalTranscript } };
  }

  // ── Action: Set Cookie ──────────────────────────────────────────────────
  function actionSetCookie(data) {
    if (!data.name || !data.value) return { success: false, error: 'Missing name or value' };
    document.cookie = `${data.name}=${data.value}; path=/`;
    return { success: true, data: { cookie_set: data.name } };
  }

  // ── Action: Set User Agent ──────────────────────────────────────────────
  function actionSetUserAgent(data) {
    if (!data.user_agent) return { success: false, error: 'Missing user_agent' };
    try {
      Object.defineProperty(navigator, 'userAgent', {
        get: function () { return data.user_agent; },
        configurable: true
      });
      return { success: true, data: { user_agent: navigator.userAgent } };
    } catch(e) {
      return { success: false, error: e.message };
    }
  }

  // ── Action: Wait Element ────────────────────────────────────────────────
  async function actionWaitElement(data) {
    const timeout = data.timeout || 5000;
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const el = findElement(data);
      if (el && isVisible(el)) {
        return { success: true, data: { found: true } };
      }
      await new Promise(r => setTimeout(r, 200));
    }
    return { success: false, error: 'Element not found within timeout' };
  }

  // ── Message Handler ─────────────────────────────────────────────────────
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type !== 'louis_action') return;

    (async () => {
      let result;
      const action = message.action;
      const data = message.data || {};

      switch (action) {
        case 'read_page':
          result = actionReadPage();
          break;
        case 'click':
          result = await actionClick(data);
          break;
        case 'type':
          result = await actionType(data);
          break;
        case 'scroll':
          result = await actionScroll(data);
          break;
        case 'get_elements':
          result = actionGetElements(data);
          break;
        case 'submit':
          result = actionSubmit(data);
          break;
        case 'start_notes':
          result = actionStartNotes();
          break;
        case 'stop_notes':
          result = actionStopNotes();
          break;
        case 'set_cookie':
          result = actionSetCookie(data);
          break;
        case 'set_user_agent':
          result = actionSetUserAgent(data);
          break;
        case 'wait_element':
          result = await actionWaitElement(data);
          break;
        default:
          result = { success: false, error: `Unknown action: ${action}` };
      }

      sendResponse(result);
    })();
    return true; // Keep message channel open for async response
  });

  // ── Expose for executeScript (Iframe bypass) ────────────────────────────
  window.louisProcessAction = async (action, data) => {
      let result;
      switch (action) {
        case 'read_page': result = actionReadPage(); break;
        case 'click': result = await actionClick(data); break;
        case 'type': result = await actionType(data); break;
        case 'scroll': result = await actionScroll(data); break;
        case 'get_elements': result = actionGetElements(data); break;
        case 'submit': result = actionSubmit(data); break;
        case 'start_notes': result = actionStartNotes(); break;
        case 'stop_notes': result = actionStopNotes(); break;
        case 'set_cookie': result = actionSetCookie(data); break;
        case 'set_user_agent': result = actionSetUserAgent(data); break;
        case 'wait_element': result = await actionWaitElement(data); break;
        default: result = { success: false, error: `Unknown action: ${action}` };
      }
      return result;
  };

  // ── Announce content script is ready ────────────────────────────────────
  try {
    chrome.runtime.sendMessage({ type: 'content_script_ready', url: window.location.href });
  } catch (e) {
    // Extension context may not be available yet
  }

})();
