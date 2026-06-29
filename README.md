# Louis Code and Browser Extension

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-1.0.0-green.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Chrome Extension](https://img.shields.io/badge/extension-Chrome-yellow)

Louis is a scoped command-line automation assistant paired with a powerful browser extension. Designed for developers, cybersecurity professionals, and power users, Louis bridges the gap between your local terminal and the web browser. It acts as an AI-driven multi-agent router that can execute coding tasks locally, orchestrate complex web searches, and physically interact with browser pages (clicking, typing, scrolling, and reading) to automate end-to-end workflows from a single unified CLI interface.

## Table of Contents
- [Key Features](#key-features)
- [Why Louis Code?](#why-louis-code)
- [Technologies Used](#technologies-used)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Screenshots](#screenshots)
- [Future Roadmap](#future-roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

## Key Features

- **Multi-Agent Routing System**: Intelligently routes tasks to specialized LLMs based on intent (e.g., coding, planning, general queries, vision tasks).
- **Web Browser Automation**: A native Chrome extension allowing Louis to navigate, click, type, read, and screenshot web pages.
- **Enhanced Web Search**: Fallback-enabled multi-provider search using Tavily, DuckDuckGo, and Google Custom Search.
- **Provider Fallback & Key Rotation**: Automatically falls back to OpenRouter on API rate limits and cycles through multiple API keys to prevent downtime.
- **Terminal UI**: Beautiful, rich terminal output with syntax highlighting, live streaming responses, and session history management.
- **Stealth Browsing**: Built-in evasions (e.g., masking `webdriver` properties) to bypass basic bot-detection during automated tasks.
- **Cross-Platform Support**: Setup scripts and native support for Windows PowerShell and Kali Linux (Bash).

## Why Louis Code?

Managing AI tools across different tabs, environments, and platforms creates friction. Louis was built to eliminate context switching by bringing a powerful, extensible AI agent directly into your terminal. Unlike standard CLI bots, Louis doesn't stop at answering questions—it can reach out into your active browser, visually inspect web pages, scrape content, and interact with web applications, making it an invaluable tool for automated pentesting, web scraping, and advanced local development.

## Technologies Used

- **Language**: Python 3.8+, JavaScript, HTML/CSS
- **Libraries/Frameworks**: `rich` (Terminal UI), `playwright`, `browser-use`, `langchain-openai`
- **APIs**: Ollama (Local/Cloud), OpenRouter, Tavily API, Google Custom Search API
- **Browser Tech**: Chrome Extensions API (Manifest V3, Service Workers, Content Scripts)

## How It Works

Louis operates via a two-part architecture communicating over WebSockets:

<details>
<summary><b>1. Python CLI Core (The Brain)</b></summary>
The main `louis.py` script parses your commands, classifies the intent, and delegates it to the best available LLM. It manages API keys, maintains conversation history, and handles local file manipulations. If a task requires browser interaction, it opens a WebSocket server on `ws://localhost:7865`.
</details>

<details>
<summary><b>2. Chrome Extension (The Hands & Eyes)</b></summary>
<ul>
  <li><b>Manifest (V3)</b>: Defines permissions (activeTab, scripting, sidePanel) and registers the background worker and content scripts.</li>
  <li><b>Background Service Worker</b>: Maintains the persistent WebSocket connection with the local Python server and relays commands.</li>
  <li><b>Side Panel / Popup</b>: Provides a visual interface within Chrome to show connection status and active tasks.</li>
  <li><b>Content Scripts</b>: Injected into web pages to execute interactions (clicking, typing, scrolling, DOM extraction) and applying stealth modifications.</li>
</ul>
</details>

## Installation

### 1. Set Up the CLI Agent

**Windows (PowerShell):**
```powershell
git clone https://github.com/anonyemichael/Louis-Code-and-Browser-Extension.git
cd Louis-Code-and-Browser-Extension
cp .env.template .env
# Edit .env and add your API keys
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

1. Open Chrome or any Chromium-based browser (Edge, Brave).
2. Navigate to `chrome://extensions`.
3. Toggle **Developer Mode** on in the top-right corner.
4. Click **Load unpacked**.
5. Select the `louis-chrome-extension` folder inside the cloned repository.
6. Pin the Louis extension to your browser toolbar for easy access.

## Usage

Start the agent from your terminal in any directory:
```bash
louis "summarize the code in this directory"
```

To enable browser automation, start the WebSocket server from inside the Louis interface:
```bash
louis> /browser
```
Then interact with the browser directly through natural language:
```bash
louis> Go to google.com, search for Python decorators, and click the first result.
louis> Scroll down and summarize the page.
```

Use `/model` to switch LLM models or `/history` to resume past sessions.

## Project Structure

```text
Louis-Code-and-Browser-Extension/
├── louis.py                    # Main CLI entry point and multi-agent router
├── web_tools.py                # Web search and content extraction utilities
├── browser_server.py           # WebSocket bridge for Chrome extension
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

## Screenshots

*(Placeholders for future screenshots)*

### Extension UI
![Extension Side Panel Placeholder](https://via.placeholder.com/600x400?text=Extension+Side+Panel+UI)

### Louis in Action
![Louis Terminal Output Placeholder](https://via.placeholder.com/800x400?text=Terminal+CLI+Execution)

## Future Roadmap

- **Enhanced DOM Understanding**: Improve content script heuristics to better handle Shadow DOMs and complex React/Vue virtual DOM elements.
- **Cross-Browser Support**: Expand manifest compatibility to fully support Firefox.
- **Automated Memory / Context Windowing**: Implement automatic summarization of past conversation history to prevent token exhaustion on long sessions.
- **Dockerized Environments**: Provide isolated Docker containers for executing generated code safely.

## Contributing

Contributions are always welcome! If you'd like to improve Louis:
1. Fork the repository.
2. Create a new feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
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
