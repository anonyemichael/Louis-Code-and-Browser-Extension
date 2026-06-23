"""
browser_server.py — WebSocket bridge between Louis CLI and the Chrome extension.

Runs a local WebSocket server on ws://localhost:7865.
The Chrome extension connects to this server and exchanges JSON messages
to let Louis browse, click, type, and read web pages.

Usage:
    From louis.py: import browser_server; browser_server.start_server(send_chat_fn)
    Standalone:    python browser_server.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from typing import Any, Callable

# ── Configuration ─────────────────────────────────────────────────────────────
WS_HOST = "0.0.0.0"
WS_PORT = int(os.environ.get("LOUIS_WS_PORT", "7865"))

# ── State ─────────────────────────────────────────────────────────────────────
_server_thread: threading.Thread | None = None
_server_loop: asyncio.AbstractEventLoop | None = None
_active_ws = None  # Currently connected WebSocket client
_send_chat_fn: Callable | None = None
_pending_results: dict[str, asyncio.Future] = {}
_result_counter = 0
_page_context: dict[str, Any] = {}


def _log(msg: str) -> None:
    """Print server log messages."""
    print(f"  [ws] {msg}")


# ── WebSocket Server (asyncio) ────────────────────────────────────────────────

async def _handle_connection(websocket):
    """Handle a single WebSocket connection from the Chrome extension."""
    global _active_ws, _page_context

    _active_ws = websocket
    _log("Chrome extension connected")

    try:
        async for raw_message in websocket:
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                _log(f"Invalid JSON received: {raw_message[:200]}")
                continue

            await _handle_message(websocket, message)

    except Exception as e:
        _log(f"Connection error: {e}")
    finally:
        if _active_ws is websocket:
            _active_ws = None
        _log("Chrome extension disconnected")


async def _handle_message(websocket, message: dict):
    """Process an incoming message from the Chrome extension."""
    global _page_context

    action = message.get("action", "")

    if action == "ping":
        await websocket.send(json.dumps({"action": "pong"}))
        return

    if action == "page_context":
        _page_context = {
            "url": message.get("url", ""),
            "title": message.get("title", ""),
            "tabId": message.get("tabId"),
        }
        return

    if action == "user_message":
        text = message.get("text", "").strip()
        page_ctx = message.get("page_context", {})
        if page_ctx:
            _page_context.update(page_ctx)

        if text:
            # Process user message through Louis AI
            asyncio.create_task(_process_user_message(websocket, text))
        return

    if action == "action_result":
        # Handle results from browser actions (click, type, etc.)
        original_action = message.get("original_action", "")
        result_key = f"result_{original_action}"

        if result_key in _pending_results:
            future = _pending_results.pop(result_key)
            if not future.done():
                future.set_result(message)
        return


async def _process_user_message(websocket, text: str):
    """Process a user message from the side panel through Louis AI."""
    global _send_chat_fn

    if not _send_chat_fn:
        await websocket.send(json.dumps({
            "action": "response",
            "text": "Louis CLI is not connected. Please run `louis` in your terminal first.",
        }))
        return

    # Build context-rich prompt
    ctx_parts = []
    if _page_context.get("url"):
        ctx_parts.append(f"Current browser tab: {_page_context['title']} ({_page_context['url']})")

    context = "\n".join(ctx_parts)
    full_prompt = f"{context}\n\nUser browser request: {text}" if context else text

    try:
        # Notify: thinking
        await websocket.send(json.dumps({
            "action": "action_start",
            "text": "Louis is thinking...",
        }))

        # Call Louis AI
        response = await asyncio.to_thread(_send_chat_fn, full_prompt)

        if response is None:
            response = "I couldn't process that request."

        # Parse response for browser actions
        browser_actions = _parse_browser_actions(response)

        if browser_actions:
            for ba in browser_actions:
                await _execute_browser_action(websocket, ba)

        # Send the text response
        # Strip any JSON tool blocks from the response for display
        display_text = response
        if "```json" in display_text:
            parts = display_text.split("```json")
            clean_parts = []
            for i, part in enumerate(parts):
                if i == 0:
                    clean_parts.append(part)
                else:
                    _, _, after = part.partition("```")
                    clean_parts.append(after)
            display_text = "".join(clean_parts).strip()

        if display_text:
            await websocket.send(json.dumps({
                "action": "response",
                "text": display_text,
            }))

    except Exception as e:
        await websocket.send(json.dumps({
            "action": "action_error",
            "text": f"Error: {str(e)}",
        }))
        await websocket.send(json.dumps({
            "action": "response",
            "text": f"Sorry, I encountered an error: {str(e)}",
        }))


def _parse_browser_actions(response_text: str) -> list[dict]:
    """Extract browser action JSON blocks from Louis's response."""
    actions = []
    if "```json" not in response_text:
        return actions

    try:
        parts = response_text.split("```json")
        for part in parts[1:]:
            json_str, _, _ = part.partition("```")
            json_str = json_str.strip()
            if json_str:
                data = json.loads(json_str)
                tool = data.get("tool", "")
                args = data.get("arguments", {})

                # Map Louis tools to browser actions
                action_map = {
                    "browse_to": "navigate",
                    "click_element": "click",
                    "type_text": "type",
                    "read_page": "read_page",
                    "scroll_page": "scroll",
                    "get_page_elements": "get_elements",
                    "submit_form": "submit",
                    "take_screenshot": "screenshot",
                    "batch_browser_actions": "multi_action",
                    "multi_action": "multi_action",
                    "new_tab": "new_tab",
                }

                if tool in action_map:
                    actions.append({
                        "action": action_map[tool],
                        **args,
                    })
    except Exception:
        pass

    return actions


async def _execute_browser_action(websocket, action: dict):
    """Send an action to the Chrome extension and wait for result."""
    action_name = action.get("action", "unknown")

    # Notify UI
    action_labels = {
        "navigate": f"Navigating to {action.get('url', '...')}",
        "click": f"Clicking: {action.get('text', action.get('selector', '...'))}",
        "type": f"Typing into: {action.get('text', action.get('selector', '...'))}",
        "read_page": "Reading page content...",
        "scroll": f"Scrolling {action.get('direction', 'down')}",
        "get_elements": "Getting page elements...",
        "screenshot": "Taking screenshot...",
        "new_tab": f"Opening new tab: {action.get('url', '...')}",
    }

    label = action_labels.get(action_name, f"Executing: {action_name}")
    await websocket.send(json.dumps({
        "action": "action_start",
        "text": label,
    }))

    # Send action to extension
    await websocket.send(json.dumps(action))

    # Wait for result (with timeout)
    result_key = f"result_{action_name}"
    future = asyncio.get_event_loop().create_future()
    _pending_results[result_key] = future

    try:
        result = await asyncio.wait_for(future, timeout=15.0)
        success = result.get("success", False)

        if success:
            await websocket.send(json.dumps({
                "action": "action_complete",
                "text": f"✓ {label.replace('...', '')} — done",
            }))
        else:
            error = result.get("error", "Unknown error")
            await websocket.send(json.dumps({
                "action": "action_error",
                "text": f"✗ {action_name}: {error}",
            }))

        return result

    except asyncio.TimeoutError:
        _pending_results.pop(result_key, None)
        await websocket.send(json.dumps({
            "action": "action_error",
            "text": f"✗ {action_name}: timed out after 15s",
        }))
        return {"success": False, "error": "Timeout"}


# ── Server Lifecycle ──────────────────────────────────────────────────────────

async def _run_server():
    """Start the WebSocket server."""
    try:
        import websockets
    except ImportError:
        _log("Installing websockets package...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import websockets

    _log(f"Starting WebSocket server on ws://localhost:{WS_PORT}")

    try:
        async with websockets.serve(
            _handle_connection,
            WS_HOST,
            WS_PORT,
            ping_interval=20,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,  # 10MB max message size
        ):
            _log(f"✓ Server running on ws://localhost:{WS_PORT}")
            _log("Waiting for Chrome extension to connect...")
            await asyncio.Future()  # Run forever
    except OSError as e:
        _log(f"⚠️ Port {WS_PORT} is already in use (is another Louis instance running?).")
        _log("Browser extension integration will be disabled for this session.")


def _server_thread_target():
    """Thread target for running the async server."""
    global _server_loop
    _server_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_server_loop)
    _server_loop.run_until_complete(_run_server())


def start_server(send_chat_fn: Callable | None = None) -> bool:
    """Start the WebSocket server in a background thread.

    Args:
        send_chat_fn: Function that takes a user prompt string and returns
                      Louis's response text. Used to process messages from
                      the Chrome extension through Louis AI.

    Returns:
        True if server started, False if already running.
    """
    global _server_thread, _send_chat_fn

    _send_chat_fn = send_chat_fn

    if _server_thread and _server_thread.is_alive():
        _log("Server is already running")
        return False

    _server_thread = threading.Thread(
        target=_server_thread_target,
        daemon=True,
        name="louis-ws-server",
    )
    _server_thread.start()

    # Give it a moment to start
    time.sleep(0.5)
    return True


def stop_server():
    """Stop the WebSocket server."""
    global _server_thread, _server_loop

    if _server_loop:
        _server_loop.call_soon_threadsafe(_server_loop.stop)
    _server_thread = None
    _server_loop = None
    _log("Server stopped")


def is_running() -> bool:
    """Check if the server is currently running."""
    return _server_thread is not None and _server_thread.is_alive()


def get_page_context() -> dict[str, Any]:
    """Get the current page context from the Chrome extension."""
    return dict(_page_context)


# ── Standalone Mode ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Louis Browser Server — ws://localhost:{WS_PORT}")
    print("Press Ctrl+C to stop.\n")

    # In standalone mode, echo messages back
    def echo_chat(prompt: str) -> str:
        print(f"  [chat] Received: {prompt[:200]}")
        return f"Echo: {prompt}"

    _send_chat_fn = echo_chat

    try:
        asyncio.run(_run_server())
    except KeyboardInterrupt:
        print("\nServer stopped.")
