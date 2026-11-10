import os, stat
from pathlib import Path
import wrapper


def test_claude_mcp_config_is_private(tmp_path):
    f = tmp_path / "provider-config" / "qa-mcp.json"
    wrapper._write_claude_mcp_config(f, "http://127.0.0.1:8200/mcp", token="secret")
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(f.parent).st_mode) == 0o700


def test_json_settings_file_is_private(tmp_path):
    f = tmp_path / "mcp_config.json"
    wrapper._write_json_mcp_settings(f, "http://127.0.0.1:8200/mcp", token="secret",
                                     server_name="scranton-visintern")
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
