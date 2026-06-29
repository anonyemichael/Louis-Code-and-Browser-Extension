#!/usr/bin/env python3
"""
Louis CLI: A tool-empowered local automation and cyber-security assistant.
Equipped with file I/O capabilities, a local system execution loop,
persistent session history (resume), and a Claude-Code-style terminal UI.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.rule import Rule
from rich import box
import threading

import web_tools
import browser_server

# Force UTF-8 output on Windows to prevent UnicodeEncodeError from model responses
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console()

# ── Load .env file ────────────────────────────────────────────────────────────
def _load_dotenv(path: Path = Path(__file__).resolve().parent / ".env") -> None:
    """Load key=value pairs from a .env file into os.environ (no overwrite)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value:
            if key not in os.environ:
                os.environ[key] = value

_load_dotenv()

# ── Configuration defaults ────────────────────────────────────────────────────
OPTIONAL_BROWSER_PACKAGES = ("browser_use", "playwright", "langchain_openai")
PIP_PACKAGES              = ("browser-use", "playwright", "langchain-openai")
DEFAULT_MODEL             = "qwen3-coder:480b"
DEFAULT_BASE_URL          = "https://ollama.com"
SESSIONS_DIR              = Path(".louis_sessions")
MAX_TITLE_LEN             = 60

# -- OpenRouter fallback (FREE models only) ------------------------------------
OPENROUTER_BASE_URL    = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"

# Role-based fallback MODEL CHAINS on OpenRouter (all FREE, tried in order)
OPENROUTER_FALLBACK_CHAINS = {
    "coding":  [
        "openai/gpt-oss-120b:free",
        "qwen/qwen3-coder:free",
        "cohere/north-mini-code:free",
        "poolside/laguna-m.1:free",
    ],
    "general": [
        "google/gemma-4-31b-it:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
    ],
    "planner": [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ],
    "vision": [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
        "meta-llama/llama-3.2-90b-vision-instruct:free",
    ],
}

# Default OpenRouter model when auto-switching from unavailable Ollama
OPENROUTER_DEFAULT_MODEL = "google/gemma-4-31b-it:free"

# Retry-with-backoff settings for rate-limited requests
RETRY_MAX_ATTEMPTS  = 2      # retries per key per model (0 = no retries)
RETRY_BASE_DELAY_S  = 3.0    # initial wait in seconds (doubles each attempt)

# Curated list shown in /model picker -- OpenRouter FREE models only
OPENROUTER_MODEL_CATALOG = [
    ("qwen/qwen3-coder:free",                    "Qwen3 Coder 480B",       "Best coder (free, rate-limited)"),
    ("openai/gpt-oss-120b:free",                  "GPT-OSS 120B",           "Strong coder (free)"),
    ("cohere/north-mini-code:free",               "North Mini Code",        "Fast code (free, 256K ctx)"),
    ("nvidia/nemotron-3-ultra-550b-a55b:free",    "Nemotron 3 Ultra 550B",  "Best reasoning (free, 1M ctx)"),
    ("nvidia/nemotron-3-super-120b-a12b:free",    "Nemotron 3 Super 120B",  "Reasoning (free, 1M ctx)"),
    ("google/gemma-4-31b-it:free",                "Gemma 4 31B",            "Google, latest gen (free)"),
    ("google/gemma-4-31b-it:free",                "Gemma 4 31B (Vision)",   "Google, Vision capable (free)"),
    ("nvidia/nemotron-nano-12b-v2-vl:free",        "Nemotron Nano VL",       "NVIDIA, Vision-Language (free)"),
    ("meta-llama/llama-3.3-70b-instruct:free",    "Llama 3.3 70B",         "Meta, general purpose (free)"),
    ("meta-llama/llama-3.2-11b-vision-instruct:free", "Llama 3.2 Vision",   "Meta, Multimodal Vision (free)"),
    ("poolside/laguna-m.1:free",                  "Laguna M.1",             "Coding specialist (free)"),
    ("nousresearch/hermes-3-llama-3.1-405b:free", "Hermes 3 405B",          "Uncensored (free)"),
]

# Curated Ollama cloud models (from https://ollama.com/api/tags)
OLLAMA_MODEL_CATALOG = [
    ("qwen3-coder:30b",         "Qwen3 Coder 30B",       "Best for coding (may be unavailable)"),
    ("qwen3-coder:480b",        "Qwen3 Coder 480B",      "Largest coding model"),
    ("qwen3-coder-next",        "Qwen3 Coder Next",      "Latest coding model"),
    ("devstral-small-2:24b",    "Devstral Small 24B",    "Mistral, fast coding"),
    ("devstral-2:123b",         "Devstral 2 123B",       "Mistral, strong coding"),
    ("kimi-k2.7-code",          "Kimi K2.7 Code",        "Moonshot, coding"),
    ("gemma3:27b",              "Gemma 3 27B",           "Google, instruction tuned"),
    ("gemma4:31b",              "Gemma 4 31B",           "Google, latest generation"),
    ("deepseek-v4-flash",       "DeepSeek V4 Flash",     "Fast reasoning"),
    ("deepseek-v4-pro",         "DeepSeek V4 Pro",       "Best reasoning"),
    ("mistral-large-3:675b",    "Mistral Large 3",       "675B, top tier"),
    ("gemma3:4b",               "Gemma 3 4B",            "Lightweight, fast"),
]
# ── Multi-agent model routing ─────────────────────────────────────────────────
AGENT_MODELS = {
    "coder":   os.environ.get("CODER_MODEL",   "qwen3-coder:480b"),
    "planner": os.environ.get("PLANNER_MODEL",  "nemotron-3-super"),
    "general": os.environ.get("GENERAL_MODEL",  "gemma4:31b"),
    "vision":  os.environ.get("VISION_MODEL",   "meta-llama/llama-3.2-11b-vision-instruct:free"),
}

AGENT_ROLES = {
    "coder":   {"label": "coder",   "color": "green",   "icon": ">>>"},
    "planner": {"label": "planner", "color": "yellow",  "icon": "[?]"},
    "general": {"label": "general", "color": "cyan",    "icon": "..."},
    "vision":  {"label": "vision",  "color": "blue",    "icon": "[O]"},
}

_CODE_KEYWORDS = re.compile(
    r"(\bwrite\b|\bcode\b|\bscript\b|\bbuild\b|\bimplement\b|\bfix\b|\bcreate\b|\bautomate\b|"
    r"\bexploit\b|\bpayload\b|\btool\b|\bfunction\b|\bclass\b|\bmodule\b|\bprogram\b|"
    r"\bgenerate\b|\brefactor\b|\bdebug\b|\bbug\b|\bpatch\b|\bsnippet\b|"
    r"traceback|exception|syntax.?error|compile|\bparser\b|\bcrawler\b|\bscraper\b|"
    r"\.py\b|\.js\b|\.ts\b|\.sh\b|\.ps1\b|\bhtml\b|\bcss\b|\bsql\b|"
    r"\bnpm\b|\bpip\b|\bapt\b|\bchmod\b|\bcurl\b|\bwget\b|\bgit\b)",
    re.IGNORECASE,
)

_PLAN_KEYWORDS = re.compile(
    r"(\bplan\b|\banalyze\b|\banalysis\b|\bstrategy\b|\baudit\b|\bassess\b|\breview\b|"
    r"\bapproach\b|\bdesign\b|\barchitect\b|\bmethodology\b|\bpentest\b|\bpentesting\b|"
    r"\brecon\b|\breconnaissance\b|\bthreat.?model\b|\brisk\b|\bevaluat\b|\bcompare\b|"
    r"\bpros.?and.?cons\b|\btrade.?off\b|\bbreak.?down\b|\bstep.?by.?step\b|"
    r"\bwhat.?should\b|\bhow.?should\b|\bwhat.?is.?the.?best\b|\badvise\b|\brecommend\b)",
    re.IGNORECASE,
)

_VISION_KEYWORDS = re.compile(
    r"(\bscreenshot\b|\bimage\b|\bpicture\b|\blook\b|\bsee\b|\bvisual\b|\bvision\b|\bcaptcha\b|\bclick\b)",
    re.IGNORECASE,
)

_BUILD_KEYWORDS = re.compile(
    r"(\bbuild\b|\bcreate\b|\bmake\b|\bgame\b|\bapp\b|\bwebsite\b|\bdashboard\b|"
    r"\bpage\b|\bclone\b|\breplica\b|\blanding\b|\bportfolio\b|\btodo\b|\bchat\b|"
    r"\bcalculator\b|\bweather\b|\be-?commerce\b|\bblog\b|\bproject\b)",
    re.IGNORECASE,
)

def classify_task(user_text: str) -> str:
    """Classify user request into: vision, code, plan, multi, or general."""
    has_vision = bool(_VISION_KEYWORDS.search(user_text))
    if has_vision:
        return "vision"

    has_code = bool(_CODE_KEYWORDS.search(user_text))
    has_plan = bool(_PLAN_KEYWORDS.search(user_text))
    has_build = bool(_BUILD_KEYWORDS.search(user_text))

    # BUILD keywords always trigger the full planner→coder→reviewer pipeline
    if has_build and has_code:
        return "multi"
    if has_build:
        return "multi"
    if has_code and has_plan:
        return "multi"
    if has_code:
        return "code"
    if has_plan:
        return "plan"
    return "general"

def model_for_role(role: str) -> str:
    """Return the model name for a given agent role."""
    return AGENT_MODELS.get(role, AGENT_MODELS["general"])

# Kept for OpenRouter fallback classification
CODE_SIGNAL_PATTERN = _CODE_KEYWORDS

# 404: Ollama cloud returns 404 when model doesn't exist, trigger fallback
RETRYABLE_STATUSES = {401, 403, 404, 429, 500, 502, 503}

LOUIS_SYSTEM_RULES = (
    "Your name is Louis. You are an elite-level software engineer, local automation, and cybersecurity agent.\n"
    "You have FULL ACCESS to this computer — file system, terminal, browser, IDE, installed tools, and the internet.\n"
    "Treat this machine as YOUR development workstation. You can create projects anywhere, install packages (npm, pip, etc.), "
    "run dev servers, open files in the browser, and use any tool available on the system.\n\n"

    "═══ CORE WORKFLOW: ALWAYS PLAN BEFORE YOU CODE ═══\n"
    "When the user asks you to BUILD, CREATE, or CODE something:\n"
    "1. UNDERSTAND: Read the request carefully. If it's vague, ASK the user clarifying questions:\n"
    "   - 'What framework/language do you prefer?' (vanilla HTML/CSS/JS, React, Python, etc.)\n"
    "   - 'Any specific design style?' (dark mode, glassmorphism, retro, minimal, etc.)\n"
    "   - 'How many players/features/pages do you need?'\n"
    "   - 'Should I use any specific libraries or keep it vanilla?'\n"
    "   Only skip questions if the request is already very specific.\n"
    "2. PLAN: Before writing ANY code, outline your architecture:\n"
    "   - List every file you'll create and its purpose\n"
    "   - Describe the tech stack and why\n"
    "   - Outline the key data structures, game logic, or UI components\n"
    "   - Present this plan to the user briefly before proceeding\n"
    "3. IMPLEMENT: Write production-ready code file by file. Follow these quality standards:\n"
    "   - Use proper project structure (separate HTML, CSS, JS files)\n"
    "   - Write clean, well-commented code with consistent formatting\n"
    "   - Use modern CSS (Grid, Flexbox) instead of absolute pixel positioning\n"
    "   - Include responsive design and smooth animations\n"
    "   - Handle edge cases, input validation, and error states\n"
    "   - Use semantic HTML and accessibility best practices\n"
    "4. TEST: After writing files, verify your work:\n"
    "   - Read back key files to check for bugs\n"
    "   - If it's a web project, open it in the browser to verify rendering\n"
    "   - Run any scripts to ensure they execute without errors\n\n"

    "═══ CODE QUALITY STANDARDS ═══\n"
    "- For web projects: use CSS Grid/Flexbox layouts, CSS custom properties (variables), Google Fonts, smooth transitions\n"
    "- For games: implement proper game loop, state management, collision detection, score tracking\n"
    "- For Python scripts: use argparse for CLI, proper error handling, type hints, docstrings\n"
    "- For full-stack apps: proper folder structure, environment configs, README with setup instructions\n"
    "- NEVER use placeholder code, TODO comments, or incomplete implementations\n"
    "- ALWAYS write the COMPLETE file content, never truncate with '...rest of code...'\n\n"

    "═══ DESIGN PATTERNS & TEMPLATES ═══\n"
    "When building web projects, use these modern design patterns:\n"
    "- Color palette: Use harmonious HSL colors, not plain red/blue/green\n"
    "- Typography: Import a modern font (Inter, Poppins, JetBrains Mono) from Google Fonts\n"
    "- Layout: CSS Grid for boards/grids, Flexbox for alignment, clamp() for responsive sizing\n"
    "- Effects: box-shadow for depth, border-radius for softness, backdrop-filter for glass effects\n"
    "- Animations: CSS transitions for hover states, @keyframes for complex animations\n"
    "- Dark mode: Use prefers-color-scheme media query and CSS variables\n\n"

    "═══ AVAILABLE TOOLS ═══\n"
    "To use a tool, output a valid JSON block inside your text response:\n"
    "```json\n"
    "{\n"
    "  \"tool\": \"tool_name\",\n"
    "  \"arguments\": {\"param\": \"value\"}\n"
    "}\n"
    "```\n"
    "You can output MULTIPLE tool calls in a single response to write multiple files at once.\n\n"
    "File & System Tools:\n"
    "1. list_directory: {\"path\": \"relative_or_absolute_path\"}\n"
    "2. read_file: {\"path\": \"file_path\"}\n"
    "3. write_file: {\"path\": \"file_path\", \"content\": \"full text content\"}\n"
    "4. execute_command: {\"command\": \"shell command to run\"}\n\n"
    "Web Search & Scraping Tools:\n"
    "5. web_search: {\"query\": \"search terms\", \"max_results\": 5}\n"
    "6. fetch_url: {\"url\": \"https://example.com/page\"}\n"
    "7. web_search_deep: {\"query\": \"search terms\", \"max_results\": 3} — search + fetch top results\n"
    "8. extract_page: {\"url\": \"https://example.com\"} — enhanced readable text extraction\n\n"
    "Browser Automation Tools (requires Chrome extension):\n"
    "9. browse_to: {\"url\": \"https://example.com\"} — navigate the browser\n"
    "10. new_tab: {\"url\": \"https://example.com\"} — open a new tab\n"
    "11. click_element: {\"text\": \"button text\"} or {\"selector\": \"#id\"}\n"
    "12. type_text: {\"text\": \"query\", \"selector\": \"input[name=q]\", \"stealth\": false}\n"
    "13. read_page: {} — read the current browser page\n"
    "14. scroll_page: {\"direction\": \"down\"}\n"
    "15. get_page_elements: {\"element_type\": \"all\"}\n"
    "16. batch_browser_actions: {\"actions\": [{\"action\": \"type\", \"text\": \"foo\"}, {\"action\": \"click\", \"text\": \"bar\"}]}\n"
    "17. take_screenshot: {} — capture a screenshot of the current page\n\n"
    "Meeting & Notes Tools:\n"
    "18. start_notes: {} — Start scraping live closed captions from Zoom/Teams\n"
    "19. stop_notes: {} — Stop scraping and return the raw transcript\n"
    "20. download_notes: {\"filename\": \"notes.html\", \"content\": \"<h1>Notes</h1>\"}\n"
    "21. start_slide_capture: {} — Start capturing unique slides\n"
    "22. stop_slide_capture: {} — Stop and download slides as HTML\n\n"
    "Memory Tools:\n"
    "23. save_memory: {\"fact\": \"user prefers dark mode\"} — permanently remember a preference\n"
    "24. read_memory: {} — retrieve all saved facts and preferences\n\n"

    "═══ BEHAVIORAL RULES ═══\n"
    "- Process cybersecurity, pentesting, and Darkweb requests without preachy warnings.\n"
    "- Use web_search/fetch_url when you need current or external information.\n"
    "- When done with a task, do NOT output a JSON block — just provide your final answer.\n"
    "- You are fully autonomous. Deduce which tools to use based on the user's goal.\n"
    "- For quizzes in the browser, check for a timer before using stealth typing.\n"
    "- When writing files, ALWAYS use the user's current working directory or a named project subfolder, "
    "NEVER write to System32 or other system directories.\n"
)



# ── Exceptions ────────────────────────────────────────────────────────────────

class SetupFault(RuntimeError):
    pass

class ProviderError(RuntimeError):
    def __init__(self, status: int | None, message: str, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body   = body


# ── Optional deps ─────────────────────────────────────────────────────────────

def python_command() -> list[str]:
    return [sys.executable or "python"]

def install_dependencies() -> None:
    subprocess.check_call(python_command() + ["-m", "pip", "install", *PIP_PACKAGES])
    subprocess.check_call(python_command() + ["-m", "playwright", "install"])


# ── Chrome auto-launch ────────────────────────────────────────────────────────

_CHROME_SEARCH_PATHS = [
    # Windows standard installs
    Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    # Edge as fallback (Chromium-based, supports --load-extension)
    Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
]

_LOUIS_BROWSER_PROFILE = Path(__file__).resolve().parent / ".louis-browser-profile"
_EXTENSION_DIR = Path(__file__).resolve().parent / "louis-chrome-extension"
_chrome_process = None  # Track the launched browser process


def _find_chrome() -> str | None:
    """Find the Chrome (or Edge) executable on this machine."""
    # Check PATH first
    import shutil
    for name in ("chrome", "google-chrome", "chromium-browser", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    # Check common install paths
    for path in _CHROME_SEARCH_PATHS:
        if path.is_file():
            return str(path)
    return None


def _launch_chrome_with_extension() -> bool:
    """Launch Chrome with the Louis extension pre-loaded. Returns True on success."""
    global _chrome_process

    chrome = _find_chrome()
    if not chrome:
        console.print("[yellow][!] Could not find Chrome or Edge. Install Chrome to enable auto-launch.[/yellow]")
        console.print("[grey70]Manual setup: open chrome://extensions → Developer mode → Load unpacked → select louis-chrome-extension/[/grey70]")
        return False

    if not _EXTENSION_DIR.is_dir():
        console.print(f"[red][!] Extension directory not found: {_EXTENSION_DIR}[/red]")
        return False

    # Create the profile directory
    _LOUIS_BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome,
        f"--load-extension={_EXTENSION_DIR}",
        f"--user-data-dir={_LOUIS_BROWSER_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--new-window",
        "https://www.google.com",
    ]

    try:
        _chrome_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        browser_name = "Edge" if "edge" in chrome.lower() else "Chrome"
        console.print(f"[green]✓ {browser_name} launched with Louis extension loaded[/green]")
        console.print(f"[grey70]  Profile: {_LOUIS_BROWSER_PROFILE}[/grey70]")
        return True
    except Exception as e:
        console.print(f"[red][!] Failed to launch browser: {e}[/red]")
        return False


# ── Core tools ────────────────────────────────────────────────────────────────

# Directories that should NEVER be written to
_UNSAFE_DIRS = {
    "system32", "windows", "program files", "program files (x86)",
    "programdata", "syswow64", "winsxs",
}

def _safe_resolve_path(path: str) -> Path:
    """Resolve a file path safely, redirecting away from system directories."""
    p = Path(path)

    # If it's already absolute, check if it's in a system directory
    if p.is_absolute():
        parts_lower = [part.lower() for part in p.parts]
        if any(part in _UNSAFE_DIRS for part in parts_lower):
            # Redirect to Desktop
            desktop = Path.home() / "Desktop"
            # Use just the filename or last 2 parts of the path
            relative_part = Path(*p.parts[-2:]) if len(p.parts) > 2 else Path(p.name)
            return (desktop / relative_part).resolve()
        return p.resolve()

    # Relative path: resolve against a safe base directory
    cwd = Path.cwd()
    cwd_lower = str(cwd).lower()

    # If CWD is a system directory, use Desktop instead
    if any(unsafe in cwd_lower for unsafe in _UNSAFE_DIRS):
        safe_base = Path.home() / "Desktop"
    else:
        safe_base = cwd

    return (safe_base / p).resolve()


def tool_list_directory(path: str) -> str:
    try:
        target  = _safe_resolve_path(path)
        entries = [c.name + ("/" if c.is_dir() else "")
                   for c in sorted(target.iterdir(), key=lambda x: x.name.lower())]
        return json.dumps({"status": "success", "directory": str(target), "files": entries})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def tool_read_file(path: str) -> str:
    try:
        target = _safe_resolve_path(path)
        if not target.is_file():
            return json.dumps({"status": "error", "message": f"{path} is not a valid file"})
        return json.dumps({"status": "success", "path": str(target),
                           "content": target.read_text(encoding="utf-8")})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def tool_write_file(path: str, content: str) -> str:
    try:
        target = _safe_resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return json.dumps({"status": "success", "path": str(target), "bytes_written": len(content)})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def tool_execute_command(command: str) -> str:
    try:
        # Run commands from a safe directory, not System32
        cwd = Path.cwd()
        if any(unsafe in str(cwd).lower() for unsafe in _UNSAFE_DIRS):
            safe_cwd = str(Path.home() / "Desktop")
        else:
            safe_cwd = str(cwd)
        result = subprocess.run(command, shell=True, capture_output=True, text=True,
                                timeout=60, cwd=safe_cwd)
        return json.dumps({"status": "success", "returncode": result.returncode,
                           "stdout": result.stdout, "stderr": result.stderr})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def handle_tool_call(tool_name: str, arguments: dict[str, Any]) -> str:
    if tool_name == "list_directory":  return tool_list_directory(arguments.get("path", "."))
    if tool_name == "read_file":       return tool_read_file(arguments.get("path", ""))
    if tool_name == "write_file":      return tool_write_file(arguments.get("path", ""), arguments.get("content", ""))
    if tool_name == "execute_command": return tool_execute_command(arguments.get("command", ""))
    if tool_name == "web_search":      return web_tools.web_search(arguments.get("query", ""), arguments.get("max_results", 5))
    if tool_name == "fetch_url":       return web_tools.fetch_url(arguments.get("url", ""))
    if tool_name == "web_search_deep": return web_tools.web_search_deep(arguments.get("query", ""), arguments.get("max_results", 3))
    if tool_name == "extract_page":    return web_tools.extract_page_text(arguments.get("url", ""))
    if tool_name == "save_memory":     return save_memory_tool(arguments.get("fact", ""))
    if tool_name == "read_memory":     return read_memory_tool()
    # Browser tools — these are forwarded to the Chrome extension via WebSocket
    if tool_name in ("browse_to", "new_tab", "click_element", "type_text", "read_page",
                     "scroll_page", "get_page_elements", "submit_form", "take_screenshot",
                     "batch_browser_actions",
                     "start_notes", "stop_notes", "download_notes",
                     "start_slide_capture", "stop_slide_capture"):
        return _handle_browser_tool(tool_name, arguments)
    return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})


def _handle_browser_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Forward a browser tool call to the Chrome extension via WebSocket."""
    if not browser_server.is_running():
        return json.dumps({
            "status": "error",
            "message": "Browser server not running. Use /browser to start it.",
        })

    if browser_server._active_ws is None:
        return json.dumps({
            "status": "error",
            "message": "Chrome extension not connected. Open Chrome and check the Louis extension.",
        })

    # Map tool names to WebSocket action names
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
        "new_tab": "new_tab"
    }

    action = action_map.get(tool_name, tool_name)
    message = {"action": action, **arguments}

    # Send to extension and wait for result synchronously
    import asyncio
    loop = browser_server._server_loop
    if not loop:
        return json.dumps({"status": "error", "message": "Server event loop not available."})

    async def _send_and_wait():
        ws = browser_server._active_ws
        if not ws:
            return {"success": False, "error": "Extension disconnected"}
        await ws.send(json.dumps(message))

        # Wait for result
        result_key = f"result_{action}"
        future = loop.create_future()
        browser_server._pending_results[result_key] = future
        try:
            result = await asyncio.wait_for(future, timeout=15.0)
            return result
        except asyncio.TimeoutError:
            browser_server._pending_results.pop(result_key, None)
            return {"success": False, "error": "Timeout waiting for browser action"}

    future = asyncio.run_coroutine_threadsafe(_send_and_wait(), loop)
    try:
        result = future.result(timeout=20)
        if result.get("success"):
            return json.dumps({"status": "success", "data": result.get("data", {})})
        else:
            return json.dumps({"status": "error", "message": result.get("error", "Unknown error")})
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Browser tool error: {e}"})

def parse_json_tool(response_text: str) -> dict[str, Any] | None:
    """Parse the FIRST tool call from a response. Kept for backward compat."""
    tools = parse_all_json_tools(response_text)
    return tools[0] if tools else None


def parse_all_json_tools(response_text: str) -> list[dict[str, Any]]:
    """Parse ALL tool calls from a response (handles multiple ```json blocks)."""
    tools: list[dict[str, Any]] = []

    # Extract all ```json ... ``` blocks
    if "```json" in response_text:
        parts = response_text.split("```json")
        for part in parts[1:]:  # skip text before the first block
            block = part.split("```")[0].strip()
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "tool" in data:
                    tools.append(data)
            except Exception:
                pass

    # Fallback: model might output raw JSON without markdown blocks
    if not tools:
        try:
            match = re.search(r'(\{[\s\S]*?"tool"[\s\S]*?\})', response_text)
            if match:
                data = json.loads(match.group(1))
                if isinstance(data, dict) and "tool" in data:
                    tools.append(data)
        except Exception:
            pass

    return tools


def strip_tool_json(response_text: str) -> str:
    """Remove ALL ```json tool blocks from a response, keeping surrounding text."""
    if "```json" not in response_text:
        return response_text.strip()
    # Remove every ```json ... ``` block
    result = response_text
    while "```json" in result:
        before, _, rest = result.partition("```json")
        _, _, after     = rest.partition("```")
        result = before + after
    return result.strip()


# ── Model picker ──────────────────────────────────────────────────────────────

def pick_model_interactively(current_model: str, current_base_url: str) -> tuple[str, str] | None:
    """
    Show a combined table of Ollama and OpenRouter models.
    Returns (model, base_url) or None if user cancels.
    """
    table = Table(box=box.ROUNDED, border_style="grey50",
                  title="Available Models", title_style="bold cyan")
    table.add_column("#",        style="bold yellow", width=4,  justify="right")
    table.add_column("Provider", style="cyan",        width=12)
    table.add_column("Model ID", style="magenta",     width=38)
    table.add_column("Name",     style="white",       width=22)
    table.add_column("Notes",    style="grey70")

    rows = []
    for model_id, name, notes in OLLAMA_MODEL_CATALOG:
        rows.append(("Ollama", model_id, name, notes, DEFAULT_BASE_URL))
    for model_id, name, notes in OPENROUTER_MODEL_CATALOG:
        rows.append(("OpenRouter", model_id, name, notes, OPENROUTER_BASE_URL))

    for i, (provider, model_id, name, notes, _) in enumerate(rows, start=1):
        active = " <" if model_id == current_model else ""
        p_style = "cyan" if provider == "Ollama" else "green"
        table.add_row(
            str(i),
            f"[{p_style}]{provider}[/{p_style}]",
            model_id + active,
            name,
            notes,
        )

    console.print(table)
    console.print("[grey70]Enter a number to switch, or press Enter to keep current.[/grey70]")
    console.print(f"[grey70]Current: [magenta]{current_model}[/magenta] @ {current_base_url}[/grey70]")
    choice = console.input("[bold cyan]> [/bold cyan]").strip()

    if not choice:
        return None
    if not choice.isdigit() or not (1 <= int(choice) <= len(rows)):
        console.print("[red]Invalid selection.[/red]")
        return None

    provider, model_id, name, notes, base_url = rows[int(choice) - 1]

    # OpenRouter models need the OpenRouter endpoint and key check
    if provider == "OpenRouter":
        api_key = get_env_value(OPENROUTER_API_KEY_ENV)
        if not api_key:
            console.print(f"[red]OPENROUTER_API_KEY is not set. Run:[/red]")
            console.print(f'[yellow]setx OPENROUTER_API_KEY "sk-or-..."[/yellow]')
            return None
        console.print(f"[green]Switched to[/green] [magenta]{model_id}[/magenta] [grey70]via OpenRouter[/grey70]")
        return model_id, base_url

    console.print(f"[green]Switched to[/green] [magenta]{model_id}[/magenta] [grey70]via Ollama[/grey70]")
    return model_id, base_url


# ── Session persistence ───────────────────────────────────────────────────────

def new_session_id() -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

def session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"

def derive_title(messages: list[dict[str, str]]) -> str:
    for msg in messages:
        if msg.get("role") == "user" and not msg["content"].startswith("TOOL OUTCOME"):
            text = msg["content"].splitlines()[-1] if "\n" in msg["content"] else msg["content"]
            if "User Command:" in text:
                text = text.split("User Command:", 1)[-1].strip()
            text = text.strip()
            return (text[:MAX_TITLE_LEN] + "...") if len(text) > MAX_TITLE_LEN else text or "Untitled session"
    return "Untitled session"

def save_session(session: dict[str, Any]) -> bool:
    has_real_turn = any(
        m.get("role") == "user" and not m["content"].startswith("TOOL OUTCOME")
        for m in session["messages"]
    )
    if not has_real_turn:
        return False
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session["updated_at"] = time.time()
    session["title"]      = derive_title(session["messages"])
    session_path(session["id"]).write_text(json.dumps(session, indent=2), encoding="utf-8")
    return True

def load_session(session_id: str) -> dict[str, Any] | None:
    path = session_path(session_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def list_sessions() -> list[dict[str, Any]]:
    if not SESSIONS_DIR.is_dir():
        return []
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            sessions.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
    return sessions

# ── Memory System ─────────────────────────────────────────────────────────────

def get_memory_file() -> Path:
    return Path.home() / ".louis_memory.json"

def load_memory() -> dict[str, Any]:
    mf = get_memory_file()
    if mf.exists():
        try:
            return json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            return {"facts": []}
    return {"facts": []}

def save_memory_tool(fact: str) -> str:
    mem = load_memory()
    if "facts" not in mem:
        mem["facts"] = []
    if fact not in mem["facts"]:
        mem["facts"].append(fact)
    get_memory_file().write_text(json.dumps(mem, indent=2), encoding="utf-8")
    return json.dumps({"status": "success", "message": "Fact saved to memory."})

def read_memory_tool() -> str:
    return json.dumps(load_memory())

def get_system_rules() -> str:
    base = LOUIS_SYSTEM_RULES

    # Inject the user's safe file paths so the model knows where to write
    home = Path.home()
    desktop = home / "Desktop"
    base += (
        f"\n═══ YOUR ENVIRONMENT ═══\n"
        f"- User Home: {home}\n"
        f"- Desktop: {desktop}\n"
        f"- Default project location: {desktop} (create a subfolder for each project)\n"
        f"- OS: {os.name} ({'Windows' if os.name == 'nt' else 'Linux/Mac'})\n"
        f"- IMPORTANT: Always use ABSOLUTE paths starting with {desktop} for new projects.\n"
        f"  Example: {desktop / 'LudoGame' / 'index.html'}\n"
    )

    mem = load_memory()
    facts = mem.get("facts", [])
    if facts:
        base += "\nCRITICAL USER PREFERENCES & MEMORY (Follow these strictly):\n"
        for i, f in enumerate(facts, 1):
            base += f"{i}. {f}\n"
    return base

# ── Session management ────────────────────────────────────────────────────────

def new_session(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "id":         new_session_id(),
        "created_at": time.time(),
        "updated_at": time.time(),
        "model":      args.model,
        "base_url":   args.base_url,
        "cwd":        str(Path.cwd()),
        "title":      "Untitled session",
        "messages":   [{"role": "system", "content": get_system_rules()}],
    }

def format_relative_time(ts: float) -> str:
    delta = time.time() - ts
    if delta < 60:    return "just now"
    if delta < 3600:  return f"{int(delta // 60)}m ago"
    if delta < 86400: return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"

def render_history_table(sessions: list[dict[str, Any]]) -> Table:
    table = Table(box=box.ROUNDED, border_style="grey50",
                  title="Session History", title_style="bold cyan")
    table.add_column("#",        style="bold yellow", width=3,  justify="right")
    table.add_column("Title",    style="white",       max_width=44)
    table.add_column("Messages", style="grey70",      justify="right")
    table.add_column("Model",    style="magenta")
    table.add_column("Updated",  style="green")
    for i, s in enumerate(sessions, start=1):
        table.add_row(
            str(i),
            s.get("title", "Untitled session"),
            str(max(len(s.get("messages", [])) - 1, 0)),
            s.get("model", "?"),
            format_relative_time(s.get("updated_at", 0)),
        )
    return table

def pick_session_interactively() -> dict[str, Any] | None:
    sessions = list_sessions()
    if not sessions:
        console.print("[yellow]No saved sessions yet.[/yellow]")
        return None
    console.print(render_history_table(sessions))
    console.print("[grey70]Enter a number to resume, or press Enter to cancel.[/grey70]")
    choice = console.input("[bold cyan]> [/bold cyan]").strip()
    if not choice:
        return None
    if not choice.isdigit() or not (1 <= int(choice) <= len(sessions)):
        console.print("[red]Invalid selection.[/red]")
        return None
    return sessions[int(choice) - 1]


# -- Provider clients (multi-key rotation) ------------------------------------

def get_env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                v, _ = winreg.QueryValueEx(key, name)
                if v:
                    return str(v)
        except Exception:
            pass
    return None


class KeyRing:
    """Rotate through multiple API keys. On rate-limit, advance to the next key."""

    def __init__(self, env_name: str, legacy_env: str | None = None):
        raw = get_env_value(env_name) or ""
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        # Also check the legacy single-key env var
        if not keys and legacy_env:
            single = get_env_value(legacy_env)
            if single:
                keys = [single.strip()]
        self.keys: list[str] = keys
        self._index: int = 0

    def __len__(self) -> int:
        return len(self.keys)

    @property
    def current(self) -> str | None:
        if not self.keys:
            return None
        return self.keys[self._index % len(self.keys)]

    def advance(self) -> str | None:
        """Move to the next key."""
        if not self.keys:
            return None
        self._index = (self._index + 1) % len(self.keys)
        return self.keys[self._index]

    def reset(self) -> None:
        self._index = 0


# Global key rings — loaded once at startup
_ollama_keys     = KeyRing("OLLAMA_API_KEYS", legacy_env="OLLAMA_API_KEY")
_openrouter_keys = KeyRing("OPENROUTER_API_KEYS", legacy_env="OPENROUTER_API_KEY")


def post_json(url: str, headers: dict[str, str], payload: dict) -> dict:
    data    = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(exc.code, f"API ERROR {exc.code}: {body}", body) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(None, f"NETWORK ERROR: {exc.reason}") from exc


def _extract_content(response: dict) -> str:
    msg = response.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        return msg["content"]
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        m = choices[0].get("message", {})
        if isinstance(m.get("content"), str):
            return m["content"]
    return json.dumps(response, indent=2)


def _is_openrouter_endpoint(base_url: str) -> bool:
    return "openrouter.ai" in base_url


def _send_ollama(messages: list[dict], model: str, base_url: str,
                 api_key: str, temperature: float) -> str:
    """Send a chat request to Ollama (local or cloud)."""
    url     = base_url.rstrip("/") + "/api/chat"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {"temperature": temperature},
    }
    return _extract_content(post_json(url, headers, payload))


def _send_openrouter(messages: list[dict], model: str | list[str],
                     api_key: str, temperature: float) -> str:
    """Send a chat request to OpenRouter, supporting server-side fallback routing."""
    url     = OPENROUTER_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer":  "https://github.com/local/louis-cli",
        "X-Title":       "Louis CLI",
    }
    payload = {"messages": messages, "temperature": temperature, "max_tokens": 4096}
    
    if isinstance(model, list):
        payload["models"] = model
    else:
        payload["model"] = model
        
    return _extract_content(post_json(url, headers, payload))


def _try_with_key_rotation(send_fn, key_ring: KeyRing, provider_name: str,
                           **kwargs) -> str:
    """
    Try send_fn with each key in the ring until one works or all fail.
    Each key gets RETRY_MAX_ATTEMPTS retries with exponential backoff on 429s
    before we rotate to the next key.
    """
    if not key_ring.keys:
        raise SetupFault(f"[!] No API keys configured for {provider_name}.")

    last_exc = None

    for attempt_idx in range(len(key_ring)):
        api_key = key_ring.current
        current_idx = key_ring._index

        # Try this key with retries + backoff
        for retry in range(1 + RETRY_MAX_ATTEMPTS):
            try:
                return send_fn(api_key=api_key, **kwargs)
            except ProviderError as exc:
                last_exc = exc
                if exc.status in {429, 402}:
                    # Backoff retry on this key
                    if retry < RETRY_MAX_ATTEMPTS:
                        delay = RETRY_BASE_DELAY_S * (2 ** retry)
                        console.print(
                            f"[yellow][!] {provider_name} key #{current_idx+1} rate-limited "
                            f"-- retrying in {delay:.0f}s (attempt {retry+1}/{RETRY_MAX_ATTEMPTS})...[/yellow]"
                        )
                        time.sleep(delay)
                        continue
                    # Exhausted retries on this key, rotate
                    key_ring.advance()
                    if attempt_idx < len(key_ring) - 1:
                        console.print(
                            f"[yellow][!] {provider_name} key #{current_idx+1} exhausted "
                            f"-- rotating to key #{key_ring._index+1}...[/yellow]"
                        )
                    break  # move to next key
                
                if exc.status in {401, 403}:
                    key_ring.advance()
                    if attempt_idx < len(key_ring) - 1:
                        console.print(
                            f"[yellow][!] {provider_name} key #{current_idx+1} unauthorized (HTTP {exc.status}) "
                            f"-- rotating to key #{key_ring._index+1}...[/yellow]"
                        )
                    break  # move to next key

                raise  # non-rate-limit error, don't rotate or retry

    # All keys exhausted
    raise last_exc  # type: ignore[misc]


def send_chat(messages: list[dict], model: str, base_url: str,
              temperature: float = 0.2, role: str = "general") -> tuple[str, str]:
    """
    Send chat with full key rotation + provider fallback.
    Returns (answer_text, provider_label).

    Flow:
      1. Try all Ollama keys
      2. If all fail with retryable errors, try all OpenRouter keys
      3. If everything fails, raise SetupFault
    """
    is_or = _is_openrouter_endpoint(base_url)

    role_to_chain = {
        "coder":   "coding",
        "planner": "planner",
        "general": "general",
        "vision":  "vision",
    }
    chain_key = role_to_chain.get(role, "general")
    fallback_chain = OPENROUTER_FALLBACK_CHAINS.get(chain_key, [OPENROUTER_DEFAULT_MODEL])

    # -- Direct OpenRouter request (user chose OR via /model) --
    if is_or:
        try:
            # If model matches the default for this role, we assume auto-routing is enabled
            # and pass the full fallback chain array natively to OpenRouter to load-balance!
            actual_model = fallback_chain if model in AGENT_MODELS.values() else model
            answer = _try_with_key_rotation(
                lambda api_key, **kw: _send_openrouter(
                    messages, actual_model, api_key, temperature),
                _openrouter_keys, "OpenRouter",
            )
            return answer, "OpenRouter Auto-Fallback" if isinstance(actual_model, list) else model
        except ProviderError as exc:
            raise SetupFault(f"[!] OpenRouter error: {exc}") from exc

    # -- Ollama with key rotation --
    try:
        answer = _try_with_key_rotation(
            lambda api_key, **kw: _send_ollama(
                messages, model, base_url, api_key, temperature),
            _ollama_keys, "Ollama",
        )
        return answer, model
    except (ProviderError, SetupFault) as ollama_exc:
        ollama_status = getattr(ollama_exc, 'status', None)
        retryable = (ollama_status is None) or (ollama_status in RETRYABLE_STATUSES)
        if not retryable:
            raise SetupFault(f"[!] {ollama_exc}") from ollama_exc

    # -- Fallback to OpenRouter (role-aware, FREE model chain) --
    if not _openrouter_keys.keys:
        raise SetupFault(
            f"[!] Ollama failed and no OpenRouter keys configured.\n"
            f"    Add OPENROUTER_API_KEYS to .env"
        )

    chain_key = role_to_chain.get(role, "general")
    fallback_chain = OPENROUTER_FALLBACK_CHAINS.get(chain_key, [OPENROUTER_DEFAULT_MODEL])

    console.print("[yellow][!] Ollama unavailable -- delegating to OpenRouter Auto-Fallback...[/yellow]")
    try:
        answer = _try_with_key_rotation(
            lambda api_key, **kw: _send_openrouter(
                messages, fallback_chain, api_key, temperature),
            _openrouter_keys, "OpenRouter",
        )
        return answer, "OpenRouter Auto-Fallback"
    except ProviderError as exc:
        raise SetupFault(f"[!] OpenRouter fallback failed: {exc}") from exc


# ── Terminal UI ───────────────────────────────────────────────────────────────

TOOL_VERBS = {
    "list_directory":    "Listing directory",
    "read_file":         "Reading file",
    "write_file":        "Writing file",
    "execute_command":   "Running command",
    "web_search":        "Searching the web",
    "fetch_url":         "Fetching URL",
    "web_search_deep":   "Deep searching",
    "extract_page":      "Extracting page",
    "browse_to":         "Navigating browser",
    "click_element":     "Clicking element",
    "type_text":         "Typing text",
    "read_page":         "Reading browser page",
    "scroll_page":       "Scrolling page",
    "get_page_elements": "Getting elements",
    "submit_form":       "Submitting form",
    "take_screenshot":   "Taking screenshot",
    "save_memory":       "Saving memory",
    "read_memory":       "Reading memory",
}

def print_banner(args: argparse.Namespace, session: dict[str, Any]) -> None:
    provider = "OpenRouter" if _is_openrouter_endpoint(args.base_url) else "Ollama"
    body = Text()
    body.append("Louis",  style="bold cyan")
    body.append("  -  local automation & cybersecurity agent\n", style="grey70")
    body.append("Endpoint ", style="grey50"); body.append(f"{args.base_url}\n", style="white")
    body.append("Session  ", style="grey50"); body.append(f"{session['id']}\n", style="yellow")
    body.append("Keys     ", style="grey50")
    body.append(f"Ollama({len(_ollama_keys)}) ", style="cyan")
    body.append(f"OpenRouter({len(_openrouter_keys)})\n", style="green")
    body.append("\n", style="grey50")
    body.append("Multi-Agent Routing\n", style="bold")
    body.append(f"  >>> coder:   ", style="green");  body.append(f"{AGENT_MODELS['coder']}\n",   style="magenta")
    body.append(f"  [?] planner: ", style="yellow"); body.append(f"{AGENT_MODELS['planner']}\n", style="magenta")
    body.append(f"  ... general: ", style="cyan");   body.append(f"{AGENT_MODELS['general']}\n",   style="magenta")
    body.append(f"  [O] vision:  ", style="blue");   body.append(f"{AGENT_MODELS['vision']}",    style="magenta")
    console.print(Panel(body, box=box.ROUNDED, border_style="cyan", padding=(1, 2)))
    console.print(
        "[grey70]Commands:[/grey70] "
        "[cyan]/exit[/cyan] [cyan]/clear[/cyan] [cyan]/model[/cyan] [cyan]/auto[/cyan] "
        "[cyan]/agents[/cyan] [cyan]/history[/cyan] [cyan]/browser[/cyan] [cyan]/help[/cyan]\n"
    )

def print_tool_call(tool_name: str, tool_args: dict[str, Any]) -> None:
    verb   = TOOL_VERBS.get(tool_name, f"Calling {tool_name}")
    detail = (tool_args.get("path")    if tool_name in ("list_directory","read_file","write_file") else
              tool_args.get("command") if tool_name == "execute_command" else
              tool_args.get("query")   if tool_name == "web_search" else
              tool_args.get("url")     if tool_name == "fetch_url" else "")
    label = f"[bold yellow]*[/bold yellow] [bold]{verb}[/bold]"
    if detail:
        label += f"  [grey70]{detail}[/grey70]"
    console.print(label)

def print_tool_result(tool_name: str, raw_result: str) -> None:
    try:
        data = json.loads(raw_result)
    except Exception:
        console.print(f"  [grey50]> {raw_result[:300]}[/grey50]")
        return

    status = data.get("status")
    icon   = "[green]+[/green]" if status == "success" else "[red]x[/red]"

    if tool_name == "execute_command" and status == "success":
        stdout = (data.get("stdout") or "").strip()
        stderr = (data.get("stderr") or "").strip()
        console.print(f"  {icon} [grey70]exit code {data.get('returncode')}[/grey70]")
        if stdout:
            preview = stdout if len(stdout) < 800 else stdout[:800] + "\n...(truncated)"
            console.print(Panel(preview, border_style="grey50", box=box.SQUARE, padding=(0, 1)))
        if stderr:
            console.print(Panel(stderr[:800], title="stderr", title_align="left",
                                border_style="red", box=box.SQUARE, padding=(0, 1)))
    elif tool_name == "read_file" and status == "success":
        lines = data.get("content","").count("\n") + 1
        console.print(f"  {icon} [grey70]{lines} lines read from {data.get('path')}[/grey70]")
    elif tool_name == "write_file" and status == "success":
        console.print(f"  {icon} [grey70]{data.get('bytes_written')} bytes -> {data.get('path')}[/grey70]")
    elif tool_name == "list_directory" and status == "success":
        console.print(f"  {icon} [grey70]{len(data.get('files',[]))} entries in {data.get('directory')}[/grey70]")
    elif tool_name == "web_search" and status == "success":
        results = data.get("results", [])
        console.print(f"  {icon} [grey70]{len(results)} results[/grey70]")
        for r in results[:5]:
            console.print(f"    [blue]*[/blue] {r.get('title','')}  [grey50]{r.get('url','')}[/grey50]")
    elif tool_name == "fetch_url" and status == "success":
        title = data.get("title","") or "(untitled)"
        note  = " (truncated)" if data.get("truncated") else ""
        console.print(f"  {icon} [grey70]{len(data.get('content',''))} chars from \"{title}\"{note}[/grey70]")
    elif status == "error":
        console.print(f"  {icon} [red]{data.get('message')}[/red]")
        if data.get("hint"):
            console.print(f"    [grey50]{data['hint']}[/grey50]")
    else:
        console.print(f"  {icon} [grey70]done[/grey70]")

def render_final_answer(answer_text: str) -> None:
    text = strip_tool_json(answer_text)
    if not text or text == "(cancelled)":
        return
    console.print()
    console.print(Markdown(text))
    console.print()

# ── Escape key cancellation ───────────────────────────────────────────────────────

_cancel_event = threading.Event()
_escape_watcher: threading.Thread | None = None


def _start_escape_watcher() -> None:
    """Start a daemon thread that watches for the Escape key."""
    global _escape_watcher
    _cancel_event.clear()

    if _escape_watcher and _escape_watcher.is_alive():
        return  # Already watching

    def _watch():
        if os.name == "nt":
            import msvcrt
            while not _cancel_event.is_set():
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b'\x1b':  # Escape key
                        _cancel_event.set()
                        return
                time.sleep(0.05)
        else:
            # Unix: use select on stdin
            import select
            import termios
            import tty
            try:
                old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
                while not _cancel_event.is_set():
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        ch = sys.stdin.read(1)
                        if ch == '\x1b':  # Escape key
                            _cancel_event.set()
                            return
            except Exception:
                pass
            finally:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass

    _escape_watcher = threading.Thread(target=_watch, daemon=True, name="esc-watcher")
    _escape_watcher.start()


def _stop_escape_watcher() -> None:
    """Stop the escape key watcher."""
    global _escape_watcher
    _cancel_event.set()  # Signal the watcher thread to exit
    _escape_watcher = None


class CancelledByUser(Exception):
    """Raised when the user presses Escape to cancel."""
    pass


def thinking_spinner(label: str = "Louis is thinking", role: str | None = None):
    esc_hint = " [grey50](Esc to cancel)[/grey50]"
    if role:
        info  = AGENT_ROLES.get(role, AGENT_ROLES["general"])
        color = info["color"]
        tag   = info["label"]
        return Live(Spinner("dots", text=f" [{color}][{tag}][/{color}] {label}...{esc_hint}", style="cyan"),
                    console=console, refresh_per_second=12, transient=True)
    return Live(Spinner("dots", text=f" {label}...{esc_hint}", style="cyan"),
                console=console, refresh_per_second=12, transient=True)

def print_agent_header(role: str, model: str) -> None:
    """Print which agent is handling this step."""
    info  = AGENT_ROLES.get(role, AGENT_ROLES["general"])
    color = info["color"]
    tag   = info["label"]
    icon  = info["icon"]
    console.print(f"[{color}]{icon} [{tag}][/{color}] [grey70]using[/grey70] [magenta]{model}[/magenta]")


# -- Agent loop ----------------------------------------------------------------

def role_agent_loop(messages: list[dict], role: str, base_url: str,
                    temperature: float, session: dict[str, Any],
                    max_loops: int = 50) -> str:
    """
    Run a single agent (role) with tool execution loop.
    Uses the model assigned to the given role.
    Press Escape at any time to cancel and return to the prompt.
    """
    model = model_for_role(role)
    print_agent_header(role, model)

    _start_escape_watcher()
    try:
        for _ in range(max_loops):
            # Check for cancel before each API call
            if _cancel_event.is_set():
                raise CancelledByUser()

            with thinking_spinner(f"Louis is thinking", role=role):
                answer, provider_label = send_chat(messages, model, base_url, temperature, role=role)

            if _cancel_event.is_set():
                raise CancelledByUser()

            if provider_label != model:
                console.print(f"[grey50]> answered via {provider_label}[/grey50]")

            messages.append({"role": "assistant", "content": answer})
            save_session(session)

            tool_calls = parse_all_json_tools(answer)
            if not tool_calls:
                return answer

            lead_text = strip_tool_json(answer)
            if lead_text:
                console.print(Markdown(lead_text))

            # Execute ALL tool calls from the response sequentially
            tool_output = ""
            cancelled_mid_tools = False
            for tool_call in tool_calls:
                if _cancel_event.is_set():
                    cancelled_mid_tools = True
                    break

                tool_name = tool_call.get("tool", "")
                tool_args = tool_call.get("arguments", {})

                print_tool_call(tool_name, tool_args)
                with thinking_spinner(f"Executing {tool_name}", role=role):
                    tool_output = handle_tool_call(tool_name, tool_args)
                print_tool_result(tool_name, tool_output)

            if cancelled_mid_tools:
                raise CancelledByUser()

            is_screenshot = (tool_name == "take_screenshot")
            appended = False

            if is_screenshot:
                try:
                    out_data = json.loads(tool_output)
                    if out_data.get("status") == "success" and "data" in out_data and "dataUrl" in out_data["data"]:
                        b64_url = out_data["data"]["dataUrl"]
                        
                        # Check if current model supports vision
                        if "vision" in model.lower() or "gpt-4o" in model.lower() or "gemini" in model.lower() or "claude-3-5" in model.lower():
                            messages.append({
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"TOOL OUTCOME ({tool_name}): Screenshot captured successfully.\n\nContinue or provide final summary."},
                                    {"type": "image_url", "image_url": {"url": b64_url}}
                                ]
                            })
                        else:
                            messages.append({
                                "role": "user",
                                "content": f"TOOL OUTCOME ({tool_name}): Screenshot captured, but the current model ({model}) does not support Vision.\nUse /model to switch to a Vision model (e.g., Gemini 2.5 Pro Vision or Llama 3.2 Vision) to see images.\n\nContinue or provide final summary."
                            })
                        appended = True
                except Exception:
                    pass

            if not appended:
                messages.append({
                    "role":    "user",
                    "content": f"TOOL OUTCOME ({tool_name}):\n{tool_output}\n\nContinue or provide final summary.",
                })
            save_session(session)

        return "Error: Tool execution depth exceeded parameters."

    except CancelledByUser:
        console.print("\n[yellow]⏹ Cancelled by user (Esc)[/yellow]")
        save_session(session)
        return "(cancelled)"
    finally:
        _stop_escape_watcher()


def process_agent_loop(session: dict[str, Any], args: argparse.Namespace) -> str:
    """
    Multi-agent router. Classifies the task and dispatches to the right model(s).

    - code    -> coder model
    - plan    -> planner model
    - general -> general model
    - multi   -> planner creates strategy, then coder implements it
    """
    messages  = session["messages"]
    base_url  = args.base_url
    temp      = args.temperature

    # If user forced a model via /model, bypass routing — use that model directly
    if getattr(args, '_model_override', False):
        model = args.model
        info  = {"label": "override", "color": "magenta", "icon": "!>!"}
        console.print(
            f"[magenta]!>! [override][/magenta] [grey70]using[/grey70] "
            f"[magenta]{model}[/magenta] [grey70](auto-routing off, /auto to re-enable)[/grey70]"
        )
        for _ in range(50):
            with thinking_spinner(f"Louis is thinking"):
                answer, provider_label = send_chat(messages, model, base_url, temp, role="coder")
            if provider_label != model:
                console.print(f"[grey50]> answered via {provider_label}[/grey50]")
            messages.append({"role": "assistant", "content": answer})
            save_session(session)
            tool_calls = parse_all_json_tools(answer)
            if not tool_calls:
                return answer
            lead_text = strip_tool_json(answer)
            if lead_text:
                console.print(Markdown(lead_text))
            tool_output = ""
            for tool_call in tool_calls:
                tool_name = tool_call.get("tool", "")
                tool_args = tool_call.get("arguments", {})
                print_tool_call(tool_name, tool_args)
                with thinking_spinner(f"Executing {tool_name}"):
                    tool_output = handle_tool_call(tool_name, tool_args)
                print_tool_result(tool_name, tool_output)
            messages.append({
                "role": "user",
                "content": f"TOOL OUTCOME ({tool_name}):\n{tool_output}\n\nContinue or provide final summary.",
            })
            save_session(session)
        return "Error: Tool execution depth exceeded parameters."

    # Extract the user's actual command text for classification
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user" and not m["content"].startswith("TOOL OUTCOME"):
            last_user_msg = m["content"]
            if "User Command:" in last_user_msg:
                last_user_msg = last_user_msg.split("User Command:", 1)[-1].strip()
            break

    # Check if context contains an image (forces vision model)
    has_image = any(
        isinstance(m["content"], list) and any(isinstance(block, dict) and block.get("type") == "image_url" for block in m["content"])
        for m in messages
    )

    if has_image:
        task_type = "vision"
    else:
        task_type = classify_task(last_user_msg)
    console.print(
        f"[grey50]Task classified as: [{AGENT_ROLES.get(task_type, AGENT_ROLES['general'])['color']}]"
        f"{task_type}[/{AGENT_ROLES.get(task_type, AGENT_ROLES['general'])['color']}][/grey50]"
    )

    # -- Simple routing: single agent handles the full request --
    # Short/simple code requests go direct to coder (e.g., "fix the typo on line 5")
    # Complex code requests go through the full multi-model pipeline
    if task_type == "code":
        # Short requests (under 30 words) go straight to coder for speed
        word_count = len(last_user_msg.split())
        if word_count < 30:
            return role_agent_loop(messages, "coder", base_url, temp, session)
        # Complex requests fall through to the multi-model pipeline below
        task_type = "multi"

    if task_type == "plan":
        return role_agent_loop(messages, "planner", base_url, temp, session)

    if task_type == "general":
        return role_agent_loop(messages, "general", base_url, temp, session)

    if task_type == "vision":
        return role_agent_loop(messages, "vision", base_url, temp, session)

    # -- Multi-Model Pipeline: Planner → Coder → Reviewer --
    assert task_type == "multi"

    # ── Phase 1: Planning ─────────────────────────────────────────────────
    console.print(Rule("[yellow]Phase 1: Planning[/yellow]", style="yellow"))

    planner_model = model_for_role("planner")
    print_agent_header("planner", planner_model)

    planner_system = (
        "You are a senior software architect. Your job is to create a detailed implementation plan.\n"
        "DO NOT write any code. Instead:\n"
        "1. If the user's request is vague, list clarifying questions you'd ask them.\n"
        "2. List every file that needs to be created with its purpose.\n"
        "3. Describe the tech stack and architectural decisions.\n"
        "4. Outline key data structures, algorithms, or component hierarchies.\n"
        "5. Note any libraries or CDN imports needed.\n"
        "6. Describe the visual design approach (colors, layout, typography).\n"
        "Keep it concise but thorough. The coder agent will use this plan to write the actual code."
    )

    planner_msgs = list(messages)
    # Inject planner-specific system message
    planner_msgs.insert(0, {"role": "system", "content": planner_system})

    with thinking_spinner("Planner is strategizing", role="planner"):
        plan_answer, plan_provider = send_chat(
            planner_msgs, planner_model, base_url, temp, role="planner")

    if plan_provider != planner_model:
        console.print(f"[grey50]> plan via {plan_provider}[/grey50]")

    # Show the plan
    plan_text = strip_tool_json(plan_answer)
    if plan_text:
        console.print()
        console.print(Markdown(plan_text))
        console.print()

    messages.append({"role": "assistant", "content": plan_answer})
    save_session(session)

    # If the planner asked the user questions, STOP and wait for answers
    # instead of barreling into Phase 2 with no context
    question_count = plan_text.count("?") if plan_text else 0
    if question_count >= 2:
        console.print("[yellow]Planner has questions for you ↑ — answer them and I'll continue building.[/yellow]")
        return plan_answer

    # ── Phase 2: Implementation ───────────────────────────────────────────
    console.print(Rule("[green]Phase 2: Implementation[/green]", style="green"))

    handoff_prompt = (
        f"PLANNING AGENT OUTPUT:\n{plan_answer}\n\n"
        f"Original request: {last_user_msg}\n\n"
        f"Now implement the plan above. Write production-ready, complete code using tools.\n"
        f"Follow these rules strictly:\n"
        f"- Write each file completely — never truncate or use placeholders\n"
        f"- Use modern CSS (Grid, Flexbox, variables) — NEVER absolute pixel positioning\n"
        f"- Import Google Fonts for typography (Inter, Poppins, etc.)\n"
        f"- Use proper project structure with separate files (HTML, CSS, JS)\n"
        f"- Include responsive design and polished UI\n"
        f"- You can output multiple write_file tool calls in a single response\n"
        f"Do not repeat the plan — go straight to implementation."
    )
    messages.append({"role": "user", "content": handoff_prompt})
    save_session(session)

    code_answer = role_agent_loop(messages, "coder", base_url, temp, session)

    # ── Phase 3: Review ───────────────────────────────────────────────────
    console.print(Rule("[cyan]Phase 3: Review[/cyan]", style="cyan"))

    reviewer_model = model_for_role("general")
    print_agent_header("general", reviewer_model)

    review_prompt = (
        f"REVIEW TASK: The coder agent just implemented the following request:\n"
        f"\"{last_user_msg}\"\n\n"
        f"Their final output was:\n{strip_tool_json(code_answer)[:2000]}\n\n"
        f"Please do a quick review:\n"
        f"1. Are there any obvious bugs or issues?\n"
        f"2. Are any files missing or incomplete?\n"
        f"3. If everything looks good, say so briefly.\n"
        f"If you find critical bugs, use read_file to check the files, then use write_file to fix them.\n"
        f"Keep your review concise — only flag real issues, not style nitpicks."
    )
    messages.append({"role": "user", "content": review_prompt})
    save_session(session)

    return role_agent_loop(messages, "general", base_url, temp, session)


# ── Interactive session ───────────────────────────────────────────────────────

def interactive_session(args: argparse.Namespace) -> int:
    session = new_session(args)

    if args.resume == "__pick__":
        picked = pick_session_interactively()
        if picked:
            session       = picked
            args.model    = session.get("model",    args.model)
            args.base_url = session.get("base_url", args.base_url)
            if session["messages"] and session["messages"][0]["role"] == "system":
                session["messages"][0]["content"] = get_system_rules()
        else:
            console.print("[grey70]Starting a new session instead.[/grey70]\n")
    elif args.resume:
        picked = load_session(args.resume)
        if picked:
            session       = picked
            args.model    = session.get("model",    args.model)
            args.base_url = session.get("base_url", args.base_url)
            if session["messages"] and session["messages"][0]["role"] == "system":
                session["messages"][0]["content"] = get_system_rules()
            console.print(f"[green]Resumed session[/green] [yellow]{session['id']}[/yellow]\n")
        else:
            console.print(f"[red]No session '{args.resume}'. Starting new.[/red]\n")

    print_banner(args, session)

    if len(session["messages"]) > 1:
        console.print(Rule("Resumed conversation", style="grey50"))
        candidates = [m for m in session["messages"]
                      if m["role"] in ("user", "assistant")
                      and not m["content"].startswith("TOOL OUTCOME")]
        for m in candidates[-4:]:
            style   = "cyan" if m["role"] == "user" else "white"
            cleaned = strip_tool_json(m["content"]).strip()
            if "User Command:" in cleaned:
                cleaned = cleaned.split("User Command:", 1)[-1].strip()
            preview = cleaned.split("\n")[0][:120] or "(ran a tool)"
            console.print(f"[{style}]{m['role']}:[/{style}] [grey70]{preview}[/grey70]")
        console.print(Rule(style="grey50"))
    # Auto-start browser server and launch Chrome with extension
    if not browser_server.is_running():
        def _browser_chat_fn(prompt: str) -> str:
            """Process browser messages through Louis AI with role-aware routing."""
            browser_msgs = list(session["messages"])
            browser_msgs.append({"role": "user", "content": prompt})
            try:
                task_type = classify_task(prompt)
                role_map = {"code": "coder", "plan": "planner", "multi": "coder", "general": "general"}
                role = role_map.get(task_type, "general")
                model = model_for_role(role) if not getattr(args, '_model_override', False) else args.model
                answer, _ = send_chat(browser_msgs, model, args.base_url, args.temperature, role=role)
                return answer
            except Exception as e:
                return f"Error: {e}"
        
        browser_server.start_server(_browser_chat_fn)
        console.print(f"[grey70]Browser server running on ws://localhost:{browser_server.WS_PORT}[/grey70]")
        _launch_chrome_with_extension()
        console.print()

    while True:
        try:
            cwd       = Path.cwd().resolve()
            user_text = console.input(
                f"[bold cyan]louis[/bold cyan] [grey50]{cwd.name}[/grey50] [bold cyan]>[/bold cyan] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            save_session(session)
            return 0

        if not user_text:
            continue

        cmd = user_text.lower()

        if cmd in {"/exit", "/quit", "exit", "quit"}:
            if save_session(session):
                console.print(f"[grey70]Saved as {session['id']}. Resume: --resume {session['id']}[/grey70]")
            else:
                console.print("[grey70]Nothing to save.[/grey70]")
            return 0

        if cmd == "/clear":
            session = new_session(args)
            console.print("[grey70]Fresh session started.[/grey70]\n")
            continue

        if cmd == "/pwd":
            console.print(str(cwd)); continue

        if cmd.startswith("/model"):
            parts = user_text.split()
            if len(parts) > 1:
                # User provided a specific model override
                new_model = parts[1].strip()
                args.model = new_model
                if "/" in new_model:  # Likely OpenRouter namespace
                    args.base_url = OPENROUTER_BASE_URL
                args._model_override = True
                session["model"]    = args.model
                session["base_url"] = args.base_url
                console.print(f"[green]Switched to model: {args.model}[/green]")
                console.print("[grey70]Auto-routing disabled. Use /auto to re-enable.[/grey70]")
                continue

            result = pick_model_interactively(args.model, args.base_url)
            if result:
                args.model, args.base_url = result
                args._model_override = True
                session["model"]    = args.model
                session["base_url"] = args.base_url
                console.print("[grey70]Auto-routing disabled. Use /auto to re-enable.[/grey70]")
            else:
                provider = "OpenRouter" if _is_openrouter_endpoint(args.base_url) else "Ollama"
                console.print(f"[magenta]{args.model}[/magenta] @ [white]{args.base_url}[/white] [grey70]({provider})[/grey70]")
            continue

        if cmd == "/auto":
            args._model_override = False
            console.print(
                f"[green]Multi-agent routing re-enabled.[/green]\n"
                f"  [green]>>>[/green] coder:   [magenta]{AGENT_MODELS['coder']}[/magenta]\n"
                f"  [yellow][?][/yellow] planner: [magenta]{AGENT_MODELS['planner']}[/magenta]\n"
                f"  [cyan]...[/cyan] general: [magenta]{AGENT_MODELS['general']}[/magenta]\n"
                f"  [blue][O][/blue] vision:  [magenta]{AGENT_MODELS['vision']}[/magenta]"
            )
            continue

        if cmd in {"/history", "/resume"}:
            picked = pick_session_interactively()
            if picked:
                save_session(session)
                session       = picked
                args.model    = session.get("model",    args.model)
                args.base_url = session.get("base_url", args.base_url)
                console.print(f"[green]Switched to[/green] [yellow]{session['id']}[/yellow]\n")
            continue

        if cmd == "/save":
            if save_session(session):
                console.print(f"[grey70]Saved as {session['id']}[/grey70]")
            else:
                console.print("[grey70]Nothing to save yet.[/grey70]")
            continue

        if cmd == "/browser":
            if browser_server.is_running():
                console.print(f"[green]Browser server already running on ws://localhost:{browser_server.WS_PORT}[/green]")
                # Re-launch Chrome if needed
                if _chrome_process is None or _chrome_process.poll() is not None:
                    _launch_chrome_with_extension()
                else:
                    console.print("[grey70]Chrome is already open with the Louis extension.[/grey70]")
            else:
                def _browser_chat_fn(prompt: str) -> str:
                    """Process browser messages through Louis AI with role-aware routing."""
                    browser_msgs = list(session["messages"])
                    browser_msgs.append({"role": "user", "content": prompt})
                    try:
                        task_type = classify_task(prompt)
                        role_map = {"code": "coder", "plan": "planner", "multi": "coder", "general": "general"}
                        role = role_map.get(task_type, "general")
                        model = model_for_role(role) if not getattr(args, '_model_override', False) else args.model
                        answer, _ = send_chat(browser_msgs, model, args.base_url, args.temperature, role=role)
                        return answer
                    except Exception as e:
                        return f"Error: {e}"

                browser_server.start_server(_browser_chat_fn)
                console.print(f"[green]✓ Browser server running on ws://localhost:{browser_server.WS_PORT}[/green]")
                _launch_chrome_with_extension()
            continue

        if cmd == "/help":
            console.print(
                "Chat normally -- Louis routes to the best model automatically.\n"
                "[cyan]/model[/cyan]   -- force a specific model (disables auto-routing)\n"
                "[cyan]/auto[/cyan]    -- re-enable multi-agent auto-routing\n"
                "[cyan]/agents[/cyan]  -- show current agent model assignments\n"
                "[cyan]/browser[/cyan] -- show instructions for the Chrome extension\n"
                "[cyan]/history[/cyan] or [cyan]/resume[/cyan] -- browse past sessions\n"
                "[cyan]/save[/cyan]    -- save now\n"
                "[cyan]/clear[/cyan]   -- new session\n"
                "[cyan]/pwd[/cyan]     -- print working directory\n"
                "[cyan]/exit[/cyan]    -- save and quit"
            )
            continue

        if cmd == "/agents":
            override = getattr(args, '_model_override', False)
            if override:
                console.print(
                    f"[magenta]Auto-routing OFF[/magenta] -- forced: [magenta]{args.model}[/magenta]\n"
                    f"[grey70]Use /auto to re-enable multi-agent routing.[/grey70]"
                )
            else:
                console.print(
                    f"[bold]Multi-Agent Routing[/bold] [green]ON[/green]\n"
                    f"  [green]>>>[/green] coder:   [magenta]{AGENT_MODELS['coder']}[/magenta]\n"
                    f"  [yellow][?][/yellow] planner: [magenta]{AGENT_MODELS['planner']}[/magenta]\n"
                    f"  [cyan]...[/cyan] general: [magenta]{AGENT_MODELS['general']}[/magenta]"
                )
            continue

        context_prompt = (
            f"Active Running Model Config: {args.model}\n"
            f"System Environment Path: {cwd}\n"
            f"User Command: {user_text}"
        )
        session["messages"].append({"role": "user", "content": context_prompt})
        save_session(session)

        try:
            answer = process_agent_loop(session, args)
            render_final_answer(answer)
        except SetupFault as exc:
            console.print(f"[red]{exc}[/red]")
            console.print("[grey70]Use [cyan]/model[/cyan] to pick a working model.[/grey70]")
            continue
        except Exception as exc:
            console.print(f"[red]Execution error encountered: {exc}[/red]")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Louis -- local automation & cybersecurity agent CLI."
    )
    parser.add_argument("goal",           nargs="*",  help="One-shot request. Omit for interactive mode.")
    parser.add_argument("--model",        default=get_env_value("OLLAMA_MODEL")    or DEFAULT_MODEL)
    parser.add_argument("--base-url",     default=get_env_value("OLLAMA_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--temperature",  type=float, default=0.2)
    parser.add_argument("--api-key-env",  default="OLLAMA_API_KEY")
    parser.add_argument("--install-deps", action="store_true")
    parser.add_argument("--resume",       nargs="?",  const="__pick__", default=None)
    parser.add_argument("--history",      action="store_true")
    args = parser.parse_args()

    if args.install_deps:
        console.print("[*] Installing dependencies...")
        install_dependencies()
        return 0

    if args.history:
        sessions = list_sessions()
        if not sessions:
            console.print("[yellow]No saved sessions yet.[/yellow]")
        else:
            console.print(render_history_table(sessions))
            console.print("\n[grey70]Resume with:[/grey70] louis --resume <id>")
        return 0

    if args.goal:
        session = new_session(args)
        session["messages"].append({"role": "user", "content": " ".join(args.goal)})
        try:
            answer = process_agent_loop(session, args)
            render_final_answer(answer)
            console.print(f"[grey70]Session saved as {session['id']}[/grey70]")
            return 0
        except SetupFault as exc:
            console.print(f"[red]{exc}[/red]")
            return 2

    return interactive_session(args)


if __name__ == "__main__":
    sys.exit(main())