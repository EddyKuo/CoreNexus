"""Phase 3 unit tests — Safe-Mode migration guard and CLI commands.

No database connection is required; all tests operate on temporary files.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import _check_safe_mode, app

runner = CliRunner()

# ── Safe-Mode Unit Tests ──────────────────────────────────────

SAFE_MIGRATION = """
def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))
    op.create_index('ix_users_phone', 'users', ['phone'])

def downgrade() -> None:
    op.drop_index('ix_users_phone', 'users')
    op.drop_column('users', 'phone')
"""

DROP_COLUMN_MIGRATION = """
def upgrade() -> None:
    op.drop_column('users', 'phone')
"""

DROP_TABLE_MIGRATION = """
def upgrade() -> None:
    op.drop_table('users')
"""

BOTH_DESTRUCTIVE_MIGRATION = """
def upgrade() -> None:
    op.drop_table('old_logs')
    op.drop_column('users', 'legacy_field')
"""


class TestSafeMode:
    def _write_migration(self, tmpdir: str, content: str) -> Path:
        path = Path(tmpdir) / "0001_test_migration.py"
        path.write_text(content, encoding="utf-8")
        return path

    def test_safe_migration_passes(self):
        """add_column / create_index do not trigger Safe-Mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = self._write_migration(tmpdir, SAFE_MIGRATION)
            # Should not raise
            _check_safe_mode(f, allow_destructive=False)

    def test_drop_column_blocked(self):
        """op.drop_column raises SystemExit(1) in strict mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = self._write_migration(tmpdir, DROP_COLUMN_MIGRATION)
            with pytest.raises(SystemExit) as exc_info:
                _check_safe_mode(f, allow_destructive=False)
            assert exc_info.value.code == 1

    def test_drop_table_blocked(self):
        """op.drop_table raises SystemExit(1) in strict mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = self._write_migration(tmpdir, DROP_TABLE_MIGRATION)
            with pytest.raises(SystemExit) as exc_info:
                _check_safe_mode(f, allow_destructive=False)
            assert exc_info.value.code == 1

    def test_multiple_destructive_ops_blocked(self):
        """Both drop_table and drop_column in one file → still blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = self._write_migration(tmpdir, BOTH_DESTRUCTIVE_MIGRATION)
            with pytest.raises(SystemExit):
                _check_safe_mode(f, allow_destructive=False)

    def test_allow_destructive_flag_bypasses_block(self):
        """With allow_destructive=True, destructive ops are allowed through."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = self._write_migration(tmpdir, DROP_COLUMN_MIGRATION)
            # Should NOT raise
            _check_safe_mode(f, allow_destructive=True)

    def test_drop_in_downgrade_only_does_not_block_upgrade(self):
        """Safe migration where drop_* only appears in downgrade block still passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = self._write_migration(tmpdir, SAFE_MIGRATION)
            _check_safe_mode(f, allow_destructive=False)

    def test_partial_word_match_not_triggered(self):
        """Words like 'dropdown' must not falsely trigger the drop_column guard."""
        content = """
def upgrade():
    # This is a dropdown widget, not a real drop_column
    pass
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = self._write_migration(tmpdir, content)
            _check_safe_mode(f, allow_destructive=False)


# ── CLI Command Tests (via Typer CliRunner) ───────────────────

class TestMigrationCLI:
    def test_cli_help_is_available(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "db" in result.output.lower()

    def test_db_subcommand_help(self):
        result = runner.invoke(app, ["db", "--help"])
        assert result.exit_code == 0
        for cmd in ("makemigrations", "migrate", "status", "downgrade"):
            assert cmd in result.output

    def test_makemigrations_requires_message(self):
        """Running makemigrations without a message should fail with non-zero exit."""
        result = runner.invoke(app, ["db", "makemigrations"])
        assert result.exit_code != 0
