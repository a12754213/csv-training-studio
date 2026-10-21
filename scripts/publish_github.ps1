# Publish this reviewed project to the signed-in user's PRIVATE GitHub repository.
[CmdletBinding()]
param([ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')][string]$RepoName = 'csv-training-studio')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
function Invoke-Git {
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "Git failed (exit $LASTEXITCODE). No force-push was attempted." }
}
try {
    Set-Location -LiteralPath $root
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Install Git first: winget install --id Git.Git -e . Then reopen this launcher.'
    }
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw 'Install GitHub CLI first: winget install --id GitHub.cli -e . Then reopen this launcher.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root '.git'))) {
        $bundle = Join-Path $root 'history\CSV_Training_Studio.bundle'
        if (-not (Test-Path -LiteralPath $bundle)) {
            throw 'Git history is missing. Download the Release ZIP with history, or clone the repository.'
        }
        $seed = Join-Path $root ('.runtime\git-import-' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $seed) | Out-Null
        Invoke-Git -GitArgs @('clone','--no-checkout','--branch','main',$bundle,$seed)
        Move-Item -LiteralPath (Join-Path $seed '.git') -Destination (Join-Path $root '.git')
        Invoke-Git -GitArgs @('remote','remove','origin')
        # Populate only Git's index; preserve all files in the user's working folder.
        Invoke-Git -GitArgs @('reset','--mixed','HEAD')
    }
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'Switch to main before publishing.' }
    $status = & git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Git status.' }
    if ($status) {
        $status | Write-Host
        throw 'Working files differ from the reviewed commit. Review and commit intended changes first; see docs/GITHUB.md.'
    }
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & gh auth status --hostname github.com
    $signedIn = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $savedPreference
    if (-not $signedIn) {
        & gh auth login --hostname github.com --git-protocol https --web --scopes 'repo,workflow'
        if ($LASTEXITCODE -ne 0) { throw 'GitHub login was not completed.' }
    }
    $account = & gh api user --jq '.login'
    if ($LASTEXITCODE -ne 0 -or -not $account) { throw 'Cannot identify the signed-in GitHub account.' }
    $repo = "$($account.Trim())/$RepoName"
    $url = "https://github.com/$repo.git"
    $remotes = @(& git remote)
    if ($remotes -contains 'origin') {
        $existingUrl = (& git remote get-url origin).Trim()
        if ($existingUrl -ne $url -and $existingUrl -ne "https://github.com/$repo") {
            throw "Existing origin points elsewhere: $existingUrl . No remote was changed."
        }
    } else {
        $savedPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & gh repo view $repo --json nameWithOwner 2>$null
        $alreadyExists = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $savedPreference
        if ($alreadyExists) {
            throw "Repository $repo already exists. Connect it manually only after confirming it is the intended project."
        }
        & gh repo create $repo --private --source $root --remote origin --description 'CSV analysis, preprocessing and baseline training with Streamlit'
        if ($LASTEXITCODE -ne 0) { throw 'Repository creation failed. Check GitHub access and repository name.' }
    }
    & gh auth setup-git --hostname github.com
    if ($LASTEXITCODE -ne 0) { throw 'Git authentication setup failed.' }
    Invoke-Git -GitArgs @('push','-u','origin','main','--tags')
    Write-Host "Published: https://github.com/$repo"
    Write-Host "Check CI and Releases: https://github.com/$repo/actions"
    Write-Host 'Next: docs/DEPLOY.md explains the Streamlit account authorization and deployment.'
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
