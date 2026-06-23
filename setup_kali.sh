#!/usr/bin/env bash
set -euo pipefail

INSTALL_PATH="${INSTALL_PATH:-$HOME/Louis-Agent}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[+] Installing Louis Agent to $INSTALL_PATH..."
if [ "$SOURCE_DIR" != "$INSTALL_PATH" ]; then
  mkdir -p "$INSTALL_PATH"
  cp -r "$SOURCE_DIR/"* "$INSTALL_PATH/"
fi

chmod +x "$INSTALL_PATH/louis.py"

if [[ "${1:-}" != "" ]]; then
  if ! grep -q '^export OLLAMA_API_KEY=' "$HOME/.bashrc" 2>/dev/null; then
    printf '\n# Louis CLI\nexport OLLAMA_API_KEY="%s"\n' "$1" >> "$HOME/.bashrc"
  fi
  export OLLAMA_API_KEY="$1"
else
  echo "[i] No API key supplied. Add this to ~/.bashrc later if needed:"
  echo '    export OLLAMA_API_KEY="your-key"'
fi

cat > "$INSTALL_PATH/louis" <<EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_PATH/louis.py" "\$@"
EOF
chmod +x "$INSTALL_PATH/louis"

echo "[+] Setting up global command 'louis'..."
if [[ -w /usr/local/bin ]]; then
  ln -sf "$INSTALL_PATH/louis" /usr/local/bin/louis
else
  sudo ln -sf "$INSTALL_PATH/louis" /usr/local/bin/louis
fi
echo "[+] Linked /usr/local/bin/louis globally"

echo "[+] Installing dependencies..."
python3 "$INSTALL_PATH/louis.py" --install-deps

echo "[+] Setup Complete!"
echo "[+] You can now use the agent globally by typing 'louis' in your terminal."
echo '    Example: louis "inspect this folder and summarize the project"'
