# Louis Code and Browser Extension

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-1.0.0-green.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Chrome Extension](https://img.shields.io/badge/extension-Chrome-yellow)

Louis is an advanced, terminal-based local automation and cybersecurity assistant paired with a native Chrome browser extension. Designed for developers, cybersecurity professionals, and power users, Louis bridges the gap between your local OS and the web browser.

It acts as an autonomous multi-agent system that routes tasks intelligently to specialized LLMs based on intent (coding, planning, general querying, or vision). From the unified CLI, Louis can edit local files, execute shell commands, perform deep web searches, and physically interact with browser pages (clicking, typing, reading DOMs, and taking screenshots). It even features a built-in memory system and meeting capture tools for Zoom and Teams.

## Table of Contents
- [Key Features](#key-features)
- [Why Louis Code?](#why-louis-code)
- [Technologies Used](#technologies-used)
- [How It Works (Architecture)](#how-it-works-architecture)
- [Agent Tools & Capabilities](#agent-tools--capabilities)
- [Installation](#installation)
- [Usage & Commands](#usage--commands)
- [Project Structure](#project-structure)
- [Future Roadmap](#future-roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

## Key Features

- **Multi-Agent Routing System**: Analyzes your prompt and automatically routes it to the best free model for the job: `coder` (e.g., Qwen3 Coder), `planner` (e.g., Nemotron 3), `general` (e.g., Gemma 4), or `vision` (e.g., Llama 3.2 Vision).
- **Web Browser Automation**: Connects to a custom Chrome extension via WebSockets. Louis can navigate, click, type stealthily, scroll, and screenshot pages for visual context.
- **Meeting & Slide Capture**: Specialized tools to scrape live closed captions from Zoom/Teams meetings and automatically capture unique slides, exporting them to HTML notes.
- **Long-Term Memory System**: Remembers user preferences and facts across sessions natively in `~/.louis_memory.json`.
- **Enhanced Web Search**: Multi-provider search with automatic fallback using Google Custom Search, Tavily API, and DuckDuckGo (HTML scraping).
- **Provider Fallback & Key Rotation**: Combines local Ollama with OpenRouter Cloud APIs. Automatically falls back to OpenRouter on API rate limits and cycles through an array of API keys to ensure zero downtime.
- **Interactive Terminal UI**: Built with `rich`, featuring beautiful syntax highlighting, live spinners, session history tables, and interactive model pickers.
- **Cross-Platform**: Automated setup scripts for Windows PowerShell (`.ps1`) and Kali Linux Bash (`.sh`).

## Why Louis Code?

Managing disjointed AI tools across different tabs creates friction. Louis eliminates context switching by placing a highly capable, extensible AI agent directly into your terminal. It doesn't just answer questions—it can reach out into your OS to execute commands, read files, and reach into your active browser to scrape data, bypass simple bot detection, and automate web workflows. It's a complete ecosystem for automated pentesting, web scraping, and advanced local development.

## Technologies Used

- **Language**: Python 3.8+, JavaScript, HTML/CSS
- **CLI Framework**: `rich` (Terminal UI), `argparse`
- **APIs**: Ollama (Local/Cloud), OpenRouter, Tavily, Google Custom Search
- **Browser Tech**: Chrome Extensions API (Manifest V3), WebSockets (`asyncio`)

## How It Works (Architecture)

Louis operates via a two-part architecture communicating over WebSockets:

<details>
<summary><b>1. Python CLI Core (The Brain)</b></summary>
The main `louis.py` script parses your commands, classifies the intent, and delegates it to the assigned LLM. It intercepts structured JSON tool calls from the LLM, executes local commands, or forwards browser-specific tools to the WebSocket server running on `ws://localhost:7865`.
</details>

<details>
<summary><b>2. Chrome Extension (The Hands & Eyes)</b></summary>
The extension runs a background Service Worker that maintains a persistent WebSocket connection to the Python CLI. Content scripts are injected into active tabs to execute DOM interactions (`click`, `type`, `scroll`), extract page text, take screenshots, and apply stealth modifications to evade bot detection.
</details>

## Agent Tools & Capabilities

Louis is equipped with **23 autonomous tools** that it can invoke dynamically based on your request:

### Local System & OS
- `list_directory`, `read_file`, `write_file`: Full workspace file I/O.
- `execute_command`: Run native shell commands and return `stdout`/`stderr`.

### Web Search & Scraping
- `web_search`: Search across Google, Tavily, and DuckDuckGo.
- `fetch_url`: Fetch and clean readable text from a URL.
- `web_search_deep`: Search and deeply extract full content from the top 3 results.
- `extract_page`: Enhanced text extraction with readability heuristics.

### Browser Automation (Requires `/browser`)
- `browse_to`, `new_tab`: Navigate the active browser.
- `click_element`, `type_text`, `submit_form`: Interact with DOM elements (supports stealth typing).
- `read_page`, `get_page_elements`: Extract DOM context for the LLM.
- `scroll_page`, `take_screenshot`: Scroll and capture visual context (automatically triggers vision models).
- `batch_browser_actions`: Queue multiple interactions in a single pass.

### Meeting & Presentation Tools
- `start_notes`, `stop_notes`, `download_notes`: Scrape and compile live closed captions from Zoom or Teams web clients.
- `start_slide_capture`, `stop_slide_capture`: Automatically detect and capture unique slides during a presentation.

### Persistent Memory
- `save_memory`, `read_memory`: Store and retrieve user preferences permanently.

## Installation

### 1. Set Up the CLI Agent

**Windows (PowerShell):**
```powershell
git clone https://github.com/anonyemichael/Louis-Code-and-Browser-Extension.git
cd Louis-Code-and-Browser-Extension
cp .env.template .env
# Edit .env and add your API keys (Ollama, OpenRouter, Tavily, etc.)
.\setup_windows.ps1
louis --install-deps
```

**Kali Linux / Debian (Bash):**
```bash
git clone https://github.com/anonyemichael/Louis-Code-and-Browser-Extension.git
cd Louis-Code-and-Browser-Extension
cp .env.template .env
# Edit .env and add your API keys
chmod +x setup_kali.sh
./setup_kali.sh
source ~/.bashrc
louis --install-deps
```

### 2. Install the Chrome Extension

1. Open Chrome or any Chromium-based browser.
2. Navigate to `chrome://extensions`.
3. Toggle **Developer Mode** on in the top-right corner.
4. Click **Load unpacked** and select the `louis-chrome-extension` folder.
5. Pin the Louis extension to your browser toolbar.

## Usage & Commands

Start the agent from your terminal in any directory:
```bash
louis "summarize the python scripts in this directory"
```

To enable browser automation, start the WebSocket server from inside the Louis interface:
```bash
louis> /browser
```
Then interact with the browser directly through natural language:
```bash
louis> Go to google.com, search for Python decorators, and take a screenshot of the results.
louis> Start taking notes from this Zoom tab.
```

### Interactive CLI Commands
- `/model` - Interactively select and force a specific model (disables auto-routing).
- `/auto` - Re-enable multi-agent auto-routing.
- `/agents` - Show current agent model assignments.
- `/browser` - Start the WebSocket server and show Chrome extension instructions.
- `/history` or `/resume` - Browse and resume past conversational sessions.
- `/save` - Save the current session manually.
- `/clear` - Start a fresh session.
- `/pwd` - Print the current working directory.
- `/exit` or `/quit` - Save and quit.

## Project Structure

```text
Louis-Code-and-Browser-Extension/
├── louis.py                    # Main CLI entry point, multi-agent router, and tool definitions
├── web_tools.py                # Multi-provider web search and HTML content extraction
├── browser_server.py           # WebSocket bridge for the Chrome extension
├── setup_windows.ps1           # Windows environment & profile setup
├── setup_kali.sh               # Linux environment & profile setup
├── .env.template               # Template for API keys and configuration
└── louis-chrome-extension/     # The Chrome Extension source code
    ├── manifest.json           # Extension Manifest V3
    ├── background.js           # Service worker handling WebSocket connection
    ├── content.js              # DOM interaction and scraping logic
    ├── stealth.js              # Bot-evasion script injected at document_start
    └── sidepanel.html          # Extension UI
```

## Future Roadmap

- **Enhanced DOM Understanding**: Improve content script heuristics to better handle Shadow DOMs and complex React/Vue virtual DOM elements.
- **Cross-Browser Support**: Expand manifest compatibility to fully support Firefox.
- **Dockerized Environments**: Provide isolated Docker containers for executing generated code safely during automated pentesting or coding tasks.

## Contributing

Contributions are always welcome! If you'd like to improve Louis:
1. Fork the repository.
2. Create a new feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add amazing feature'`).
4. Push to the branch (`git origin feature/amazing-feature`).
5. Open a Pull Request.

Please ensure your code follows the existing style and all new features are documented.

## License

This project is open-source and available under the MIT License.

## Author

**Anonye Michael Ayinterima**  
*Computer Engineering Student at UENR*  
*Software Engineer*  
*Founder of StayHub Ghana*  

- **GitHub:** [https://github.com/anonyemichael](https://github.com/anonyemichael)
- **LinkedIn:** [Insert LinkedIn URL here]
