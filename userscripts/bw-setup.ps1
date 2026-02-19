# Bitwarden setup helper for Windows

Write-Host "=== Bitwarden Setup for qutebrowser ===" -ForegroundColor Cyan

Write-Host "`n1. Configure server (optional)..." -ForegroundColor Yellow
Write-Host "Run this only if you use a self-hosted server:"
Write-Host "bw config server <your-server-url>"

Write-Host "`n2. Check login status..." -ForegroundColor Yellow
$status = bw status | ConvertFrom-Json
if ($status.status -eq "unauthenticated") {
    Write-Host "Not logged in. Run: bw login <your-email>" -ForegroundColor Red
    exit 1
}

Write-Host "`n3. Unlock vault..." -ForegroundColor Yellow
$masterPassword = Read-Host "Enter Bitwarden master password" -AsSecureString
$securePtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($masterPassword)
$masterPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($securePtr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($securePtr)

try {
    $session = bw unlock $masterPasswordPlain --raw
    if ($session) {
        $env:BW_SESSION = $session
        [System.Environment]::SetEnvironmentVariable("BW_SESSION", $session, "User")
        Write-Host "Session saved to user environment variable BW_SESSION." -ForegroundColor Green
    } else {
        Write-Host "Failed to get session key from bw unlock." -ForegroundColor Red
    }
} catch {
    Write-Host "Error unlocking vault: $_" -ForegroundColor Red
}

Write-Host "`n4. Verify..." -ForegroundColor Yellow
try {
    $test = bw list items --session $env:BW_SESSION | ConvertFrom-Json
    Write-Host "Success. Vault items available: $($test.Count)" -ForegroundColor Green
} catch {
    Write-Host "Verification failed: $_" -ForegroundColor Red
}

Write-Host "`nUse keybind 'pw' in qutebrowser to autofill."
