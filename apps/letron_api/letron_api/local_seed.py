"""Bridge the root workspace seed script into Bench execute."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def run() -> None:
    seed_path = Path(__file__).parents[3] / "bootstrap-seed.py"
    spec = importlib.util.spec_from_file_location("workspace_bootstrap_seed", seed_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load seed script: {seed_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run()
