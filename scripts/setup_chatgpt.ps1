$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot 'start.ps1') -SetupOnly
    if ($LASTEXITCODE -ne 0) { throw 'Base environment setup failed.' }
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $uv = Join-Path $projectRoot '.runtime\uv\uv.exe'
    & $uv pip install --python $python --no-config -c (Join-Path $projectRoot 'requirements.lock.txt') -r (Join-Path $projectRoot 'requirements-mcp.txt')
    if ($LASTEXITCODE -ne 0) { throw 'MCP dependency installation failed.' }
    & $python (Join-Path $PSScriptRoot 'configure_chatgpt.py')
    if ($LASTEXITCODE -ne 0) { throw 'Configuration generation failed.' }
    Write-Host 'Ready. See docs/CHATGPT_LOCAL.md for the one-time ChatGPT connection.'
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
