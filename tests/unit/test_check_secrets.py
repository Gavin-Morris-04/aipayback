"""The commit hook must block keys and .env files. Fake keys are built at runtime so this
test file itself never contains anything secret-looking."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_secrets.py"
spec = importlib.util.spec_from_file_location("check_secrets", SCRIPT)
check_secrets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_secrets)

FAKE_ANTHROPIC = "sk-" + "ant-" + "api03-" + "A" * 40
FAKE_GITHUB = "gh" + "p_" + "B" * 36


def test_blocks_anthropic_key(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text(f"my key is {FAKE_ANTHROPIC}\n")
    assert check_secrets.main([str(f)]) == 1


def test_blocks_github_token(tmp_path):
    f = tmp_path / "ci.yml"
    f.write_text(f"token: {FAKE_GITHUB}\n")
    assert check_secrets.main([str(f)]) == 1


def test_blocks_anthropic_variable_and_filled_app_key(tmp_path):
    f = tmp_path / "setup.sh"
    f.write_text("export ANTHROPIC_API_KEY=abc\n")
    assert check_secrets.main([str(f)]) == 1
    g = tmp_path / "config.env.txt"
    g.write_text("AIPAYBACK_API_KEY=realvalue\n")
    assert check_secrets.main([str(g)]) == 1


def test_blocks_env_files_but_not_example(tmp_path):
    assert check_secrets.main([str(tmp_path / ".env")]) == 1
    assert check_secrets.main([str(tmp_path / ".env.local")]) == 1
    example = tmp_path / ".env.example"
    example.write_text("AIPAYBACK_API_KEY=\n")
    assert check_secrets.main([str(example)]) == 0


def test_clean_file_passes(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("print('no secrets here')\n")
    assert check_secrets.main([str(f)]) == 0
