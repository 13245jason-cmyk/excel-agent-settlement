import sys
import pytest
from tools import create_user


def test_account_tool_outputs_only_hash_and_quotes_dotted_username(monkeypatch, capsys):
    password = "synthetic-operator-password"
    monkeypatch.setattr(sys, "argv", ["create_user.py", "--username", "team.owner", "--environment", "staging"])
    monkeypatch.setattr(create_user.getpass, "getpass", lambda prompt: password)
    create_user.main()
    output = capsys.readouterr().out
    assert password not in output
    assert '[users."team.owner"]' in output
    assert 'environment = "staging"' in output
    assert 'password_hash = "pbkdf2_sha256$600000$' in output


def test_account_tool_rejects_password_mismatch(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["create_user.py", "--username", "owner", "--environment", "production"])
    answers = iter(["synthetic-password-one", "synthetic-password-two"])
    monkeypatch.setattr(create_user.getpass, "getpass", lambda prompt: next(answers))
    with pytest.raises(SystemExit) as exc:
        create_user.main()
    assert exc.value.code == 2
    assert "password_hash" not in capsys.readouterr().out
