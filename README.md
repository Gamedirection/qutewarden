# qutewarden

Minimal qutebrowser + Bitwarden integration for Windows.

## What This Repo Includes

- `userscripts/qute-bitwarden.py`
  - Fetches credentials from Bitwarden CLI (`bw`) for the active page URL.
  - Supports:
    - `pw` combined fill (username then `<Tab>` then password)
    - `pU` username-only fill into active field
    - `pW` password-only fill into active field
  - If multiple logins match a URL, prompts you to choose one.
- `userscripts/qute-bitwarden.cmd`
  - Windows wrapper that runs the Python userscript.
- `userscripts/bw-setup.ps1`
  - Helper script to unlock Bitwarden and set `BW_SESSION`.
- `install.ps1`
  - Safe installer that avoids overwriting user files and appends only missing keybinds.

## Prerequisites

- Windows
- qutebrowser installed
- Python available in `PATH`
- Bitwarden CLI (`bw`) installed and in `PATH`
  - Download: https://bitwarden.com/download/#command-line-interface

## Setup

1. Run the installer (recommended):

```powershell
.\install.ps1
```

The installer is non-destructive:
- does not overwrite existing user files
- appends only missing qutewarden keybind lines to `config.py`

2. Ensure Bitwarden session is available:

```powershell
bw login <your-email>
bw unlock --raw
```

Set the returned value to `BW_SESSION` in your shell/session (or user environment).

3. Restart qutebrowser.

## Manual Setup (optional)

```powershell
Copy-Item -Force .\userscripts\qute-bitwarden.py "$env:APPDATA\qutebrowser\data\userscripts\qute-bitwarden.py"
Copy-Item -Force .\userscripts\qute-bitwarden.cmd "$env:APPDATA\qutebrowser\data\userscripts\qute-bitwarden.cmd"
```

Add keybinds to qutebrowser `config.py`:

```python
config.bind('pw', "message-info 'loading...';; spawn --userscript qute-bitwarden.cmd combo-start", mode='normal')
config.bind('pU', 'spawn --userscript qute-bitwarden.cmd user-active', mode='normal')
config.bind('pW', 'spawn --userscript qute-bitwarden.cmd pass-active', mode='normal')
```

## Usage

- `pw`: combined flow for username + password.
- `pU`: fill username in currently active input.
- `pW`: fill password in currently active input.
- If multiple accounts match, choose from the selector prompt in qutebrowser.

## Security Notes

- Do not commit secrets.
- Keep `.env` local only.
- `BW_SESSION` is sensitive and should be rotated/re-unlocked as needed.
