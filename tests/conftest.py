"""Pytest configuration — sets required env vars before any module is imported."""
import os

# auth.py reads SECRET_KEY at module import time; set it here so all tests pass.
# Tests that specifically test the missing-key behaviour must use monkeypatch to
# temporarily remove it AND reload the module inside a pytest.raises block.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-64hexchars00")
