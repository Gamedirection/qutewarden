[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Copy-IfMissing([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Missing source file: $Source"
    }

    if (Test-Path -LiteralPath $Destination) {
        $srcHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash
        $dstHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash
        if ($srcHash -eq $dstHash) {
            Write-Host "Unchanged: $Destination"
            return
        }

        $candidate = "$Destination.qutewarden.new"
        Copy-Item -Force -LiteralPath $Source -Destination $candidate
        Write-Warning "Preserved existing file: $Destination"
        Write-Warning "Wrote candidate update: $candidate"
        return
    }

    Copy-Item -LiteralPath $Source -Destination $Destination
    Write-Host "Installed: $Destination"
}

function Ensure-BitwardenCli {
    if (Get-Command bw -ErrorAction SilentlyContinue) {
        Write-Host "Bitwarden CLI found: $(bw --version)"
        return
    }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Step "Installing Bitwarden CLI via winget"
        winget install --id Bitwarden.CLI --exact --accept-source-agreements --accept-package-agreements
        if (Get-Command bw -ErrorAction SilentlyContinue) {
            Write-Host "Bitwarden CLI installed: $(bw --version)"
            return
        }
        Write-Warning "winget install finished but 'bw' is still not in PATH for this shell. Restart terminal and run install.ps1 again."
        return
    }

    Write-Warning "Could not auto-install Bitwarden CLI (winget not available)."
    Write-Warning "Install manually: https://bitwarden.com/download/#command-line-interface"
}

function Append-MissingBindings([string]$ConfigPath) {
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        Set-Content -LiteralPath $ConfigPath -Encoding UTF8 -Value "config.load_autoconfig(False)`r`n"
    }

    $content = Get-Content -LiteralPath $ConfigPath -Raw

    $bindings = @(
        @{
            Key = 'pw'
            Line = 'config.bind(''pw'', "message-info ''loading...'';; spawn --userscript qute-bitwarden.cmd combo-start", mode=''normal'')'
        },
        @{
            Key = 'pU'
            Line = 'config.bind(''pU'', ''spawn --userscript qute-bitwarden.cmd user-active'', mode=''normal'')'
        },
        @{
            Key = 'pW'
            Line = 'config.bind(''pW'', ''spawn --userscript qute-bitwarden.cmd pass-active'', mode=''normal'')'
        }
    )

    $toAppend = New-Object System.Collections.Generic.List[string]

    foreach ($binding in $bindings) {
        $keyPattern = "config\.bind\('$([regex]::Escape($binding.Key))',"
        if ($content -match $keyPattern) {
            Write-Host "Skipped existing bind for key '$($binding.Key)' in config.py"
            continue
        }

        if ($content -match [regex]::Escape($binding.Line)) {
            Write-Host "Already present: $($binding.Key)"
            continue
        }

        $toAppend.Add($binding.Line)
    }

    if ($toAppend.Count -eq 0) {
        Write-Host "No config changes needed."
        return
    }

    $block = @(
        "",
        "# qutewarden (added by install.ps1)",
        "# Only missing binds were added. Existing user binds were preserved."
    ) + $toAppend

    Add-Content -LiteralPath $ConfigPath -Encoding UTF8 -Value ($block -join "`r`n")
    Write-Host "Appended $($toAppend.Count) qutewarden bind(s) to: $ConfigPath"
}

Step "qutewarden install start"

$repoRoot = Split-Path -Parent $PSCommandPath
$sourceUserscripts = Join-Path $repoRoot 'userscripts'

$appdata = $env:APPDATA
if (-not $appdata) {
    throw 'APPDATA is not set.'
}

$quteConfigDir = Join-Path $appdata 'qutebrowser\config'
$quteDataUserscriptsDir = Join-Path $appdata 'qutebrowser\data\userscripts'
$configPath = Join-Path $quteConfigDir 'config.py'

Ensure-Directory -Path $quteConfigDir
Ensure-Directory -Path $quteDataUserscriptsDir

Ensure-BitwardenCli

Step "Installing userscripts (non-destructive)"
Copy-IfMissing -Source (Join-Path $sourceUserscripts 'qute-bitwarden.py') -Destination (Join-Path $quteDataUserscriptsDir 'qute-bitwarden.py')
Copy-IfMissing -Source (Join-Path $sourceUserscripts 'qute-bitwarden.cmd') -Destination (Join-Path $quteDataUserscriptsDir 'qute-bitwarden.cmd')
Copy-IfMissing -Source (Join-Path $sourceUserscripts 'bw-setup.ps1') -Destination (Join-Path $quteDataUserscriptsDir 'bw-setup.ps1')

Step "Merging qutebrowser config (append-only)"
Append-MissingBindings -ConfigPath $configPath

Step "Done"
Write-Host "Next: run 'bw login <email>' then 'bw unlock --raw' and set BW_SESSION."
