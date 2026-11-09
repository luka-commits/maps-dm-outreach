#!/usr/bin/env python3
"""check.py - is this machine ready? Prints a check mark or a cross per item, with the exact fix.

  python3 setup/check.py              # all offline checks
  python3 setup/check.py --online     # plus a free, authenticated Apify request
  python3 setup/check.py --init-config   # create outreach.config.json from the example if missing
  python3 setup/check.py --json       # machine-readable result

Uses the standard library only, so it also runs before the virtual environment exists. Secrets are
never printed. Exit code 1 if a required check fails (optional ones only warn).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
MIN_NODE = (22, 13)
SETUP = "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"


def check(id_, label, ok, detail="", fix="", required=True):
    return {"id": id_, "label": label, "ok": bool(ok), "required": required, "detail": detail, "fix": fix}


def read_env_file() -> dict:
    out = {}
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip("\"'")
    return out


def apify_token() -> str:
    return os.environ.get("APIFY_TOKEN") or read_env_file().get("APIFY_TOKEN", "")


def check_python():
    v = sys.version_info
    return check("python", "Python 3.10 or newer", v >= (3, 10), f"found {v.major}.{v.minor}.{v.micro}",
                 "Install Python 3.10+ (https://www.python.org/downloads/ or `brew install python`)")


def check_venv():
    if not VENV_PYTHON.exists():
        return check("venv", "Virtual environment with dependencies", False, ".venv not found", SETUP)
    proc = subprocess.run([str(VENV_PYTHON), "-c", "import modal, httpx"], capture_output=True, text=True)
    return check("venv", "Virtual environment with dependencies", proc.returncode == 0,
                 ".venv has modal and httpx" if proc.returncode == 0 else "modal or httpx missing in .venv",
                 ".venv/bin/pip install -r requirements.txt")


def node_version():
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"v(\d+)\.(\d+)", out.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_node():
    v = node_version()
    if v is None:
        return check("node", "Node 22.13 or newer", False, "node not found",
                     "Install Node 22.13+ (https://nodejs.org or `brew install node`)")
    return check("node", "Node 22.13 or newer (built-in SQLite)", v >= MIN_NODE, f"found {v[0]}.{v[1]}",
                 "Update Node to 22.13 or newer (https://nodejs.org or `brew upgrade node`)")


def check_app_modules():
    ok = (ROOT / "app" / "node_modules").is_dir()
    return check("app", "App dependencies installed", ok, "app/node_modules present" if ok else "app/node_modules missing",
                 "cd app && npm install")


def modal_binary():
    beside = ROOT / ".venv" / "bin" / "modal"
    return str(beside) if beside.exists() else shutil.which("modal")


def modal_authenticated() -> bool:
    if os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"):
        return True
    config = pathlib.Path(os.environ.get("MODAL_CONFIG_PATH") or pathlib.Path.home() / ".modal.toml")
    if not config.is_file():
        return False
    text = config.read_text(encoding="utf-8", errors="ignore")
    return bool(re.search(r"token_id\s*=\s*['\"]\w", text) and re.search(r"token_secret\s*=\s*['\"]\w", text))


def check_modal():
    binary = modal_binary()
    if not binary:
        return [check("modal", "Modal CLI installed", False, "modal not found", SETUP)]
    authed = modal_authenticated()
    return [check("modal", "Modal CLI installed", True, "found"),
            check("modal-auth", "Modal authenticated", authed, "token configured" if authed else "no token",
                  f"{'.venv/bin/modal' if '.venv' in binary else 'modal'} setup   (opens the browser, create a free account first at https://modal.com)")]


def check_apify(online: bool):
    token = apify_token()
    out = [check("apify-token", "APIFY_TOKEN set (optional: activity check and openers)", bool(token),
                 "found (not shown)" if token else "not set, those two steps are skipped",
                 "Copy .env.example to .env and put APIFY_TOKEN=... in it (token: https://console.apify.com/account/integrations)",
                 required=False)]
    if online and token:
        out.append(apify_online(token))
    return out


def _get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def apify_online(token):
    try:
        me = _get("https://api.apify.com/v2/users/me", token).get("data", {})
        plan = (me.get("plan") or {}).get("id") or me.get("plan") or "unknown"
        detail = f"token valid, plan {plan}"
        try:
            lim = _get("https://api.apify.com/v2/users/me/limits", token).get("data", {})
            cap = (lim.get("limits") or {}).get("maxMonthlyUsageUsd")
            used = (lim.get("current") or {}).get("monthlyUsageUsd")
            if cap is not None and used is not None:
                detail += f", ${max(cap - used, 0):.2f} of ${cap:.2f} monthly credit left"
        except (urllib.error.URLError, ValueError, OSError):
            pass
        return check("apify-online", "Apify token accepted (free request)", True, detail, required=False)
    except urllib.error.HTTPError as e:
        return check("apify-online", "Apify token accepted (free request)", False, f"HTTP {e.code}",
                     "Create a new token at https://console.apify.com/account/integrations and update .env", required=False)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return check("apify-online", "Apify token accepted (free request)", False, f"no connection ({e})",
                     "Check your internet connection and run again", required=False)


def check_config(init: bool):
    path, example = ROOT / "outreach.config.json", ROOT / "outreach.config.example.json"
    if not path.exists() and init and example.exists():
        shutil.copyfile(example, path)
    if not path.exists():
        return check("config", "outreach.config.json", False, "not created yet (defaults from the example apply)",
                     "python3 setup/check.py --init-config", required=False)
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return check("config", "outreach.config.json", False, f"invalid JSON: {e}",
                     "Fix the JSON syntax in outreach.config.json (or delete it and run --init-config)")
    return check("config", "outreach.config.json", True, "parses")


def check_data_writable():
    data = ROOT / "data"
    try:
        data.mkdir(exist_ok=True)
        probe = data / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        return check("data", "data/ is writable", True, str(data.relative_to(ROOT)) + "/")
    except OSError as e:
        return check("data", "data/ is writable", False, str(e), "Fix the permissions of the data/ folder")


def run_checks(online=False, init_config=False) -> list[dict]:
    results = [check_python(), check_venv(), check_node(), check_app_modules(), *check_modal(),
               *check_apify(online), check_config(init_config), check_data_writable()]
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", action="store_true", help="also verify the Apify token with a free request")
    ap.add_argument("--init-config", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    results = run_checks(a.online, a.init_config)
    failed = [r for r in results if not r["ok"] and r["required"]]
    if a.json:
        print(json.dumps({"ok": not failed, "checks": results}, indent=2))
    else:
        for r in results:
            mark = "✓" if r["ok"] else ("✗" if r["required"] else "!")
            print(f"{mark} {r['label']}" + (f"  ({r['detail']})" if r["detail"] else ""))
            if not r["ok"] and r["fix"]:
                print(f"    fix: {r['fix']}")
        print("\nAll required checks passed." if not failed else f"\n{len(failed)} required check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
