import json
import subprocess
import sys

from setup import check as chk


def test_json_output_has_fix_for_every_failure():
    out = subprocess.run([sys.executable, "setup/check.py", "--json"], capture_output=True, text=True, cwd=chk.ROOT)
    data = json.loads(out.stdout)
    assert {"ok", "checks"} <= set(data)
    for c in data["checks"]:
        assert {"id", "label", "ok", "required", "detail", "fix"} <= set(c)
        if not c["ok"]:
            assert c["fix"]
    assert out.returncode == (0 if data["ok"] else 1)


def test_apify_token_is_never_printed(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "apify_api_SECRETSECRET")
    results = chk.check_apify(online=False)
    assert results[0]["ok"] and "SECRET" not in json.dumps(results)


def test_missing_token_is_only_a_warning(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.setattr(chk, "read_env_file", lambda: {})
    r = chk.check_apify(online=False)[0]
    assert not r["ok"] and not r["required"]


def test_modal_auth_detection(monkeypatch, tmp_path):
    cfg = tmp_path / "modal.toml"
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.setenv("MODAL_CONFIG_PATH", str(cfg))
    assert not chk.modal_authenticated()
    cfg.write_text('[default]\ntoken_id = "ak-123"\ntoken_secret = "as-456"\n')
    assert chk.modal_authenticated()
