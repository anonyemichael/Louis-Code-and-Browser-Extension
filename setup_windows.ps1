param(
    [Parameter(Mandatory = $false)]
    [string]$OllamaApiKey,

    [Parameter(Mandatory = $false)]
    [string]$InstallPath = "C:\Users\atubt\Documents\Codex\Louis-Agent"
)

$ErrorActionPreference = "Stop"

$BundledPython = "C:\Users\atubt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
}
elseif (Test-Path -LiteralPath $BundledPython) {
    $PythonExe = $BundledPython
}
else {
    $PythonExe = "python"
    Write-Host "[!] Python was not found on PATH. Install Python or edit the louis function after setup."
}

if ($OllamaApiKey) {
    [Environment]::SetEnvironmentVariable("OLLAMA_API_KEY", $OllamaApiKey, "User")
    $env:OLLAMA_API_KEY = $OllamaApiKey
    Write-Host "[+] OLLAMA_API_KEY saved to the current user's environment."
}
else {
    Write-Host "[i] No API key supplied. Set it later with:"
    Write-Host '    [Environment]::SetEnvironmentVariable("OLLAMA_API_KEY", "your-key", "User")'
}

if (!(Test-Path -LiteralPath $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}

$LouisPy = Join-Path $InstallPath "louis.py"
$FunctionLine = "function louis { & `"$PythonExe`" `"$LouisPy`" @args }"
$ProfileText = Get-Content -LiteralPath $PROFILE -Raw -ErrorAction SilentlyContinue

if ($ProfileText -notmatch [regex]::Escape($FunctionLine)) {
    Add-Content -LiteralPath $PROFILE -Value ""
    Add-Content -LiteralPath $PROFILE -Value "# Louis CLI"
    Add-Content -LiteralPath $PROFILE -Value $FunctionLine
    Write-Host "[+] Added louis function to $PROFILE"
}
else {
    Write-Host "[i] louis function already exists in $PROFILE"
}

Write-Host "[+] Open a new PowerShell window, then run:"
Write-Host "    louis `"inspect this folder and summarize the project`""
Write-Host ""
Write-Host "[i] Optional dependency install:"
Write-Host "    louis --install-deps"
