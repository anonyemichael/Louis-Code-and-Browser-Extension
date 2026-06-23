# Louis Agent

Louis is a scoped command-line automation assistant for the current working directory.
It can run with a headless browser through `browser-use` and an OpenAI-compatible
cloud model endpoint configured by environment variables.

## Files

- `louis.py` - main CLI script.
- `web_tools.py` - multi-provider web search (Tavily, DuckDuckGo, Google CSE).
- `browser_server.py` - WebSocket bridge for the Chrome extension.
- `louis-chrome-extension/` - Chrome extension for browser automation.
- `setup_windows.ps1` - PowerShell profile and API-key setup helper.
- `setup_kali.sh` - Bash setup helper for Kali/Linux.

## Windows PowerShell

```powershell
cd "C:\Users\atubt\Documents\Codex\Louis-Agent"
.\setup_windows.ps1 -OllamaApiKey "your-key"
louis --install-deps
louis "inspect this folder and summarize the project"
```

If you do not pass the key to the setup script, set it later:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_API_KEY", "your-key", "User")
```

The setup script appends a function like this to `$PROFILE`. If `python` is not
on PATH, it uses the bundled Codex Python detected on this machine:

```powershell
function louis { & "python-or-detected-python.exe" "C:\Users\atubt\Documents\Codex\Louis-Agent\louis.py" @args }
```

## Kali Linux Bash

```bash
cd ~/Louis-Agent
chmod +x setup_kali.sh
./setup_kali.sh "your-key"
source ~/.bashrc
louis --install-deps
louis "inspect this folder and summarize the project"
```

Manual API key setup:

```bash
echo 'export OLLAMA_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc
```

Manual system link:

```bash
chmod +x louis.py
sudo ln -sf "$HOME/Louis-Agent/louis" /usr/local/bin/louis
```

## Configuration

Default model:

- `qwen3-coder:30b` for strong free local coding work through Ollama.
- Use cloud models (e.g. `gpt-4o`, `deepseek-chat`) by pointing the Ollama configuration to an OpenAI-compatible Cloud API.

### Custom Cloud APIs (via the Ollama Provider)

In both the CLI and the Chrome Extension, the **"Ollama"** provider slot is dual-purpose:
1. **Local Server:** If no API key is provided, it connects to a local Ollama instance (default `http://localhost:11434/api/chat`).
2. **Cloud APIs:** If you provide an API key and a Base URL (e.g., `https://api.deepseek.com`, `https://open.bigmodel.cn`), Louis dynamically overrides local formatting and routes your requests as standard OpenAI payloads to `${OLLAMA_BASE_URL}/v1/chat/completions`.

Environment variables:
- `OLLAMA_API_KEYS` - Comma-separated API keys for your Cloud API. Leave empty for local Ollama.
- `OLLAMA_MODEL` - Your target model (e.g., `qwen3-coder:30b` or `deepseek-chat`).
- `OLLAMA_BASE_URL` - Cloud API root URL (e.g., `https://api.deepseek.com`) or local `http://localhost:11434`.

Cloud API Example:

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_API_KEYS", "sk-your-cloud-key", "User")
$env:OLLAMA_MODEL = "deepseek-chat"
$env:OLLAMA_BASE_URL = "https://api.deepseek.com"
louis "build a small CLI project"
```

---

## Chrome Extension — Louis Web Agent

Louis includes a Chrome extension that lets Louis browse the web for you — clicking,
typing, scrolling, and reading web pages, similar to Claude's or Antigravity's browser
extension.

### Setup

1. **Start Louis** in your terminal:
   ```
   louis
   ```

2. **Start the browser server** inside the Louis CLI:
   ```
   /browser
   ```
   This starts a local WebSocket server on `ws://localhost:7865`.

3. **Install the Chrome extension**:
   - Open `chrome://extensions` in Chrome
   - Enable **Developer mode** (top right toggle)
   - Click **Load unpacked** → select the `louis-chrome-extension/` folder
   - Pin the Louis extension in your toolbar

4. **Use it**:
   - Click the Louis icon → the side panel opens
   - Green dot = connected to Louis CLI
   - Type commands like:
     - "Go to google.com and search for Python tutorials"
     - "Click the first result"
     - "Read this page and summarize it"
     - "Fill out the contact form"
     - "Scroll down"

### Features

| Feature | How it works |
|---------|-------------|
| **Navigate** | Louis opens URLs in your active tab |
| **Click** | Finds elements by text, CSS selector, or ARIA label and clicks them |
| **Type** | Fills in input fields with proper event dispatch (React/Vue compatible) |
| **Read** | Extracts visible text, links, buttons, and form fields from the page |
| **Scroll** | Scrolls up/down/to specific elements |
| **Screenshot** | Captures the visible viewport |
| **Visual Feedback** | Highlights elements with a cyan border before interacting |

### Architecture

```
Chrome Extension (Side Panel + Content Script)
        ↕  WebSocket (ws://localhost:7865)
Louis CLI (browser_server.py ↔ louis.py ↔ AI models)
```

---

## Enhanced Web Search

Louis now supports multiple search providers with automatic fallback:

1. **Tavily** (primary) — Set `TAVILY_API_KEY` in `.env` for reliable structured results
2. **DuckDuckGo** (default) — Works without any API key (HTML scraping)
3. **Google Custom Search** (optional) — Set `GOOGLE_API_KEY` + `GOOGLE_CSE_ID`

New tools available to Louis:
- `web_search_deep` — Search + fetch and extract content from top results
- `extract_page` — Enhanced text extraction with readability heuristics
