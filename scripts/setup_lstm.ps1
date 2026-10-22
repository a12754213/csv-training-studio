$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup_chatgpt.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Base and MCP setup failed.' }
    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $uv = Join-Path $projectRoot '.runtime\uv\uv.exe'
    & $uv pip install --python $python --no-config -c (Join-Path $projectRoot 'requirements.lock.txt') -r (Join-Path $projectRoot 'requirements-lstm.txt')
    if ($LASTEXITCODE -ne 0) { throw 'TensorFlow dependency installation failed.' }
    & $python -c "import tensorflow as tf; print('TensorFlow:', tf.__version__); print('GPU devices:', tf.config.list_physical_devices('GPU'))"
    if ($LASTEXITCODE -ne 0) { throw 'TensorFlow import failed.' }
    Write-Host 'LSTM ready. Native Windows normally uses CPU; NVIDIA GPU requires a separate WSL2 setup.'
    Write-Host 'Restart your ChatGPT MCP server and START_WINDOWS.bat.'
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
