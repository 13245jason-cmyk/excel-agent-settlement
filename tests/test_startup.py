"""Exercise cold login screens in fresh interpreters, without report libraries."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("environment,entry", [
    ("production", "app.py"),
    ("staging", "staging_app.py"),
])
def test_cold_login_does_not_load_report_libraries(environment, entry):
    root = Path(__file__).parents[1]
    script = """
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
from authentication import hash_password

environment, entry = sys.argv[1:]
at = AppTest.from_file(Path(entry), default_timeout=30)
at.secrets['deployment'] = {'environment': environment}
at.secrets['users'] = {'startup_test': {
    'password_hash': hash_password('synthetic-startup-password-2026'),
    'environments': [environment],
}}
at.run()
assert not at.exception, at.exception
assert at.text_input(key='login_username').label == '帳號'
assert at.text_input(key='login_password').label == '密碼'
assert len(at.get('file_uploader')) == 0
assert len(at.dataframe) == 0
assert any(c.value == '版本：mobile-upload-v1' for c in at.caption)
loaded = [m for m in ('pandas', 'openpyxl', 'member_commission') if m in sys.modules]
assert not loaded, f'Login unnecessarily loaded report libraries: {loaded}'
"""
    result = subprocess.run(
        [sys.executable, "-c", script, environment, entry],
        cwd=root, capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
