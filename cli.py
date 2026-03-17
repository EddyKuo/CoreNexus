#!/usr/bin/env python
"""CoreNexus Migration CLI — wraps Alembic with Safe-Mode protection."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(help="CoreNexus database management CLI")
db_app = typer.Typer(help="Database migration commands")
app.add_typer(db_app, name="db")

_DESTRUCTIVE_PATTERNS = [
    r"\bop\.drop_table\b",
    r"\bop\.drop_column\b",
]


def _find_latest_migration() -> Path | None:
    versions_dir = Path("alembic/versions")
    if not versions_dir.exists():
        return None
    files = sorted(versions_dir.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _extract_upgrade_block(content: str) -> str:
    """Return only the upgrade() function body so downgrade() drops don't false-positive."""
    match = re.search(r"def upgrade\(\).*?(?=\ndef |\Z)", content, re.DOTALL)
    return match.group(0) if match else content


def _check_safe_mode(migration_file: Path, allow_destructive: bool) -> None:
    content = _extract_upgrade_block(migration_file.read_text(encoding="utf-8"))
    found = []
    for pattern in _DESTRUCTIVE_PATTERNS:
        if re.search(pattern, content):
            found.append(pattern.replace(r"\b", "").replace("\\", ""))

    if not found:
        return

    typer.echo(f"\n⚠️  Safe-Mode: Destructive operations detected in {migration_file.name}:")
    for op in found:
        typer.echo(f"   • {op}")

    if allow_destructive:
        typer.echo("   --allow-destructive flag set: proceeding anyway.\n")
    else:
        typer.echo(
            "\n   Blocked. Review the migration script manually, then re-run with"
            " --allow-destructive if intentional.\n"
        )
        raise SystemExit(1)


@db_app.command("status")
def db_status():
    """Show current migration status."""
    subprocess.run(["alembic", "current"], check=True)
    subprocess.run(["alembic", "history", "--verbose"], check=True)


@db_app.command("makemigrations")
def db_makemigrations(
    message: str = typer.Argument(..., help="Human-readable migration message"),
    allow_destructive: bool = typer.Option(False, "--allow-destructive", help="Allow drop_table/drop_column"),
):
    """Generate a new Alembic migration script via autogenerate."""
    result = subprocess.run(
        ["alembic", "revision", "--autogenerate", "-m", message],
        check=True,
    )

    migration_file = _find_latest_migration()
    if migration_file is None:
        typer.echo("⚠️  Could not locate generated migration file for safety check.")
        return

    _check_safe_mode(migration_file, allow_destructive)
    typer.echo(f"✓ Migration created: {migration_file.name}")


@db_app.command("migrate")
def db_migrate():
    """Apply all pending migrations (alembic upgrade head)."""
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    typer.echo("✓ Database is up to date.")


@db_app.command("downgrade")
def db_downgrade(
    revision: str = typer.Argument("-1", help="Target revision or '-1' for one step back"),
):
    """Downgrade the database by one revision (or to a specific revision)."""
    subprocess.run(["alembic", "downgrade", revision], check=True)


if __name__ == "__main__":
    app()
