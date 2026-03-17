from __future__ import annotations

import yaml
from pathlib import Path

from pydantic import ValidationError

from src.core.models.schema_def import ModelSchema


class SchemaParser:
    """Scan a directory of YAML blueprints and validate each one."""

    def __init__(self, blueprints_dir: str | Path = "blueprints") -> None:
        self.blueprints_dir = Path(blueprints_dir)

    def load_all(self) -> list[ModelSchema]:
        if not self.blueprints_dir.exists():
            raise SystemExit(f"Blueprints directory not found: {self.blueprints_dir}")

        schemas: list[ModelSchema] = []
        yaml_files = sorted(self.blueprints_dir.glob("*.yaml"))

        if not yaml_files:
            raise SystemExit(f"No YAML blueprint files found in: {self.blueprints_dir}")

        for path in yaml_files:
            schema = self._load_file(path)
            schemas.append(schema)

        # Ensure model names are unique
        names = [s.model_name for s in schemas]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise SystemExit(f"Duplicate model_name(s) found across blueprints: {duplicates}")

        return schemas

    def _load_file(self, path: Path) -> ModelSchema:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SystemExit(f"Invalid YAML in blueprint '{path}': {exc}") from exc

        try:
            return ModelSchema.model_validate(raw)
        except ValidationError as exc:
            raise SystemExit(
                f"Blueprint validation failed for '{path}':\n{exc}"
            ) from exc
