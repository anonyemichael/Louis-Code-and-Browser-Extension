// ── Stealth Mode / Anti-Cheat Bypass ────────────────────────────────────
// Runs in the 'MAIN' world at 'document_start' before any page scripts.
// This intercepts and nullifies visibility change and blur events.

(() => {
  // 1. Intercept visibilitychange on capture phase
  document.addEventListener('visibilitychange', e => e.stopImmediatePropagation(), true);
  window.addEventListener('visibilitychange', e => e.stopImmediatePropagation(), true);
  
  // 2. Intercept blur/focusout on capture phase
  window.addEventListener('blur', e => e.stopImmediatePropagation(), true);
  document.addEventListener('blur', e => e.stopImmediatePropagation(), true);
  window.addEventListener('focusout', e => e.stopImmediatePropagation(), true);
  document.addEventListener('focusout', e => e.stopImmediatePropagation(), true);
  
  // 3. Override getters
  Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
  Object.defineProperty(document, 'hidden', { get: () => false });
  Object.defineProperty(document, 'hasFocus', { value: () => true });

  // 4. Defeat mouseleave/mouseout tracking (common in exams)
  document.addEventListener('mouseleave', e => e.stopImmediatePropagation(), true);
  window.addEventListener('mouseleave', e => e.stopImmediatePropagation(), true);
  document.documentElement.addEventListener('mouseleave', e => e.stopImmediatePropagation(), true);
  
  // 5. Freeze properties so anti-cheat can't easily overwrite them
  Object.defineProperty(window, 'onblur', { set: function() {}, get: function() { return null; } });
  Object.defineProperty(document, 'onvisibilitychange', { set: function() {}, get: function() { return null; } });
})();
