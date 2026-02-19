#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def fifo_message(fifo_path: str, command: str) -> None:
    with open(fifo_path, "w", encoding="utf-8") as fifo:
        fifo.write(command)


def fifo_commands(fifo_path: str, commands) -> None:
    fifo_message(fifo_path, " ;; ".join(commands))


def fifo_run_many(fifo_path: str, commands) -> None:
    with open(fifo_path, "w", encoding="utf-8") as fifo:
        for command in commands:
            fifo.write(command + "\n")
            fifo.flush()


def qmsg(text: str) -> str:
    return text.replace("'", "")


def fake_key_chars(text: str):
    commands = []
    for char in text:
        sequence = '" "' if char == " " else f"\\{char}"
        commands.append(f"fake-key {sequence}")
    return commands


def ensure_active_field_command(field: str) -> str:
    field_js = json.dumps(field, ensure_ascii=True)
    script = f"""
(() => {{
  const field = {field_js};
  const editable = (el) => {{
    if (!el) return false;
    if (el.disabled || el.readOnly) return false;
    if (el.tagName === 'INPUT' && (el.type || '').toLowerCase() === 'hidden') return false;
    return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable;
  }};
  const ae = document.activeElement;
  if (editable(ae)) return true;

  let target = null;
  if (field === 'pass') {{
    target = document.querySelector("input[type='password']:not([disabled]):not([readonly])");
  }} else {{
    target = document.querySelector("input:not([type='password']):not([type='hidden']):not([disabled]):not([readonly]), textarea:not([disabled]):not([readonly])");
  }}
  if (!target) {{
    target = document.querySelector("input:not([type='hidden']):not([disabled]):not([readonly]), textarea:not([disabled]):not([readonly])");
  }}
  if (!target) return false;
  try {{ target.focus(); }} catch (_) {{ return false; }}
  try {{ if (typeof target.click === 'function') target.click(); }} catch (_) {{}}
  return editable(document.activeElement);
}})();
""".strip()
    return f"jseval --quiet {json.dumps(script, ensure_ascii=True)}"


def selection_state_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "qutebrowser" / "data"
    else:
        base = Path.home() / ".local" / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "qute-bw-select.json"


def load_selection_state() -> dict:
    path = selection_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_selection_state(state: dict) -> None:
    path = selection_state_path()
    if state:
        path.write_text(json.dumps(state), encoding="utf-8")
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def clear_selection_state() -> None:
    save_selection_state({})


def fetch_items_for_url(url: str, session_key: str):
    cmd = ["bw", "list", "items", "--url", url, "--session", session_key]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def fetch_items_for_page(fifo_path: str, url: str):
    if not url:
        fifo_message(fifo_path, "message-error 'No active URL to query Bitwarden.'")
        return None

    if not shutil.which("bw"):
        fifo_message(fifo_path, "message-error 'Bitwarden CLI (bw) not found in PATH.'")
        return None

    session_key = os.environ.get("BW_SESSION")
    if not session_key:
        fifo_message(fifo_path, "message-error 'BW_SESSION is not set. Run: bw unlock'")
        return None

    fifo_message(fifo_path, "message-info 'bw: loading credentials...'")
    try:
        items = fetch_items_for_url(url, session_key)
    except subprocess.CalledProcessError as exc:
        error_msg = (exc.stderr or "").strip()
        if "Vault is locked" in error_msg or "Invalid session" in error_msg:
            fifo_message(fifo_path, "message-error 'Bitwarden session expired. Run: bw unlock'")
        else:
            fifo_message(fifo_path, "message-error 'Bitwarden command failed'")
        return None

    if not items:
        fifo_message(fifo_path, "message-warning 'No Bitwarden login found for this URL.'")
        return None
    return items


def value_for_field(fifo_path: str, login: dict, field: str) -> str:
    value = login.get("username", "") if field == "user" else login.get("password", "")
    if not value:
        if field == "user":
            fifo_message(fifo_path, "message-warning 'No username found in selected login.'")
        else:
            fifo_message(fifo_path, "message-warning 'No password found in selected login.'")
        return ""
    return value


def prompt_for_account_selection(fifo_path: str, url: str, items, action: str) -> int:
    ids = [str(item.get("id", "")) for item in items if item.get("id")]
    if not ids:
        fifo_message(fifo_path, "message-error 'Bitwarden returned entries without IDs.'")
        return 1
    save_selection_state({"action": action, "url": url, "ids": ids})

    commands = ["message-info 'bw: multiple accounts found, choose one:'"]
    preview = items[:8]
    for i, item in enumerate(preview, start=1):
        name = qmsg(str(item.get("name", "unnamed")))
        login = item.get("login", {}) or {}
        user = qmsg(str(login.get("username", "")))
        commands.append(f"message-info '{i}) {name} | {user}'")
    commands.append("message-info 'Type number and Enter'")
    commands.append("cmd-set-text -s :spawn --userscript qute-bitwarden.cmd select ")
    fifo_run_many(fifo_path, commands)
    return 0


def resolve_login_for_action(fifo_path: str, url: str, action: str):
    items = fetch_items_for_page(fifo_path, url)
    if not items:
        return None, 1
    if len(items) == 1:
        return (items[0].get("login", {}) or {}), 0
    rc = prompt_for_account_selection(fifo_path, url, items, action)
    return None, rc


def fill_active_value(fifo_path: str, value: str, label: str, field: str) -> int:
    if not value:
        return 1
    commands = [ensure_active_field_command(field), "mode-enter insert", *fake_key_chars(value), f"message-info 'Inserted {label}'"]
    fifo_run_many(fifo_path, commands)
    return 0


def perform_action_with_login(fifo_path: str, action: str, login: dict) -> int:
    if action in ("user-active", "user-start", "start-user"):
        value = value_for_field(fifo_path, login, "user")
        if not value:
            return 1
        return fill_active_value(fifo_path, value, "username", "user")

    if action in ("pass-active", "pass-start", "start-pass"):
        value = value_for_field(fifo_path, login, "pass")
        if not value:
            return 1
        return fill_active_value(fifo_path, value, "password", "pass")

    if action in ("combo-start", "start-combo"):
        username = value_for_field(fifo_path, login, "user")
        if not username:
            return 1
        password = value_for_field(fifo_path, login, "pass")
        if not password:
            return 1
        commands = [
            ensure_active_field_command("user"),
            "mode-enter insert",
            *fake_key_chars(username),
            "fake-key <Tab>",
            *fake_key_chars(password),
            "message-info 'Inserted username + password'",
        ]
        fifo_run_many(fifo_path, commands)
        return 0

    fifo_message(fifo_path, "message-error 'Unknown Bitwarden action'")
    return 1


def handle_select_phase(fifo_path: str, index_arg: str) -> int:
    state = load_selection_state()
    if not state:
        fifo_message(fifo_path, "message-error 'No pending Bitwarden selection.'")
        return 1

    try:
        idx = int(index_arg)
    except ValueError:
        fifo_message(fifo_path, "message-error 'Selection must be a number.'")
        return 1

    ids = state.get("ids", [])
    if idx < 1 or idx > len(ids):
        fifo_message(fifo_path, "message-error 'Selection out of range.'")
        return 1

    url = str(state.get("url", ""))
    action = str(state.get("action", ""))
    selected_id = str(ids[idx - 1])

    items = fetch_items_for_page(fifo_path, url)
    if not items:
        return 1
    selected = next((item for item in items if str(item.get("id", "")) == selected_id), None)
    if not selected:
        fifo_message(fifo_path, "message-error 'Selected account not found. Run command again.'")
        clear_selection_state()
        return 1

    clear_selection_state()
    return perform_action_with_login(fifo_path, action, selected.get("login", {}) or {})


def main() -> int:
    phase = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    fifo_path = os.environ.get("QUTE_FIFO")
    url = os.environ.get("QUTE_URL", "")
    if not fifo_path:
        print("This script must be run from qutebrowser.")
        return 1

    if phase in ("combo-start", "start-combo"):
        fifo_message(fifo_path, "message-info 'loading...'")

    if phase in ("user-active", "user-start", "start-user", "pass-active", "pass-start", "start-pass", "combo-start", "start-combo"):
        login, rc = resolve_login_for_action(fifo_path, url, phase)
        if rc != 0:
            return rc
        if login is None:
            return 0
        return perform_action_with_login(fifo_path, phase, login)

    if phase == "select":
        if len(sys.argv) < 3:
            fifo_message(fifo_path, "message-error 'Usage: ... qute-bitwarden.cmd select <number>'")
            return 1
        return handle_select_phase(fifo_path, sys.argv[2])

    fifo_message(fifo_path, "message-info 'Use pw (auto) or pU/pW (manual)'")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
