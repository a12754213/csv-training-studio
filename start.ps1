# Compatible with Windows PowerShell 5.1 and PowerShell 7. ASCII for 5.1 encoding.
[CmdletBinding()]
param(
    [switch]$SetupOnly,
    [switch]$NoBrowser,
    [ValidateRange(0,65535)][int]$Port = 0
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = $PSScriptRoot
$venvDir = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$runtimeDir = Join-Path $projectRoot '.runtime'
$uvExe = Join-Path $runtimeDir 'uv\uv.exe'
$uvVersion = '0.13.4'
$uvArchiveSha256 = 'ccec7508a07d9933d7cb1261880633efcf1f30d6e6eddab21823f1dae6f23225'
$requirements = Join-Path $projectRoot 'requirements.lock.txt'
$marker = Join-Path $venvDir '.requirements.sha256'

function Invoke-Uv {
    param([string[]]$UvArgs)
    & $uvExe @UvArgs
    if ($LASTEXITCODE -ne 0) { throw "uv failed (exit $LASTEXITCODE). See the error above." }
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Use start.sh on Linux/macOS.' }
    $architecture = $env:PROCESSOR_ARCHITECTURE
    if ($env:PROCESSOR_ARCHITEW6432) { $architecture = $env:PROCESSOR_ARCHITEW6432 }
    if ($architecture -ne 'AMD64') { throw 'This one-click launcher requires 64-bit Intel/AMD Windows. See docs/LOCAL.md for manual setup.' }
    Set-Location -LiteralPath $projectRoot
    $requiredHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    $ready = $false
    if ((Test-Path -LiteralPath $venvPython) -and (Test-Path -LiteralPath $marker)) {
        $storedHash = (Get-Content -LiteralPath $marker -Raw).Trim()
        if ($storedHash -eq $requiredHash) {
            & $venvPython (Join-Path $projectRoot 'scripts\check_environment.py') --quiet
            $ready = ($LASTEXITCODE -eq 0)
        }
    }
    if (-not $ready) {
        Write-Host 'Preparing the project environment. First setup needs internet access.'
        Write-Host 'Python, packages and download cache will stay inside this project.'
        New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
        # Process-local settings; no PATH, registry or Conda changes.
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $runtimeDir 'python'
        $env:UV_PYTHON_BIN_DIR = Join-Path $runtimeDir 'bin'
        $env:UV_CACHE_DIR = Join-Path $runtimeDir 'cache'
        $env:UV_PYTHON_INSTALL_REGISTRY = '0'
        $env:UV_PYTHON_INSTALL_BIN = '0'
        if (-not (Test-Path -LiteralPath $uvExe)) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $archive = Join-Path $runtimeDir 'uv-download.zip'
            $url = "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-x86_64-pc-windows-msvc.zip"
            Write-Host "Downloading uv $uvVersion from its official release..."
            Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
            $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
            if ($actualHash -ne $uvArchiveSha256) { throw 'uv download checksum mismatch. Download was not executed.' }
            $extractDir = Join-Path $runtimeDir 'uv'
            Expand-Archive -LiteralPath $archive -DestinationPath $extractDir -Force
            if (-not (Test-Path -LiteralPath $uvExe)) { throw 'uv.exe is missing from the downloaded archive.' }
        }
        if (-not (Test-Path -LiteralPath $venvDir)) {
            Invoke-Uv -UvArgs @('python','install','3.12','--no-bin','--no-registry','--no-config')
            Invoke-Uv -UvArgs @('venv','--python','3.12','--managed-python','--seed','--no-config',$venvDir)
        }
        if (-not (Test-Path -LiteralPath $venvPython)) {
            throw 'Existing .venv is incomplete. Rename .venv to .venv-backup, then start again.'
        }
        & $venvPython -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)'
        if ($LASTEXITCODE -ne 0) { throw 'Existing .venv is not usable Python 3.12. Rename .venv to .venv-backup, then start again.' }
        Invoke-Uv -UvArgs @('pip','sync','--python',$venvPython,'--no-config',$requirements)
        & $venvPython (Join-Path $projectRoot 'scripts\check_environment.py')
        if ($LASTEXITCODE -ne 0) { throw 'Environment validation failed.' }
        Set-Content -LiteralPath $marker -Value $requiredHash -Encoding ASCII
    }
    Write-Host 'Environment ready.'
    if ($SetupOnly) { exit 0 }
    $launchArgs = @((Join-Path $projectRoot 'scripts\serve.py'))
    if ($NoBrowser) { $launchArgs += '--no-browser' }
    if ($Port -ne 0) { $launchArgs += @('--port', "$Port") }
    & $venvPython @launchArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Keep this window open and copy the message. See docs/LOCAL.md.'
    exit 1
}
