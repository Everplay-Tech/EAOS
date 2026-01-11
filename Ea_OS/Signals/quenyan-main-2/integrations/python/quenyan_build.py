"""Setuptools integration that transparently encodes Quenyan packages."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable

from setuptools.command.build_py import build_py as _build_py  # type: ignore


def _run_quenyan(args: Iterable[str], cwd: Path) -> None:
    cmd = [os.environ.get("QUENYAN_CLI", "quenyan"), *args]
    process = subprocess.run(cmd, cwd=str(cwd), check=False)
    if process.returncode != 0:
        raise SystemExit(f"Quenyan command failed: {' '.join(cmd)}")


class build_py(_build_py):
    """Custom build command that emits .qyn1 artefacts alongside modules."""

    user_options = _build_py.user_options + [
        ("quenyan-passphrase=", None, "Passphrase used to encode modules"),
        ("quenyan-keyfile=", None, "Path to key file"),
    ]

    def initialize_options(self) -> None:  # type: ignore[override]
        super().initialize_options()
        self.quenyan_passphrase = None
        self.quenyan_keyfile = None

    def finalize_options(self) -> None:  # type: ignore[override]
        super().finalize_options()
        if not self.quenyan_passphrase and not self.quenyan_keyfile:
            key_path = Path(".quenyan/keys/master.key")
            if key_path.exists():
                self.quenyan_keyfile = str(key_path)

    def run(self) -> None:  # type: ignore[override]
        super().run()
        package_root = Path(self.build_lib)
        sources = list(package_root.rglob("*.py"))
        if not sources:
            return
        args = [
            "encode-project",
            str(package_root / "qyn-packages"),
            *map(str, sources),
        ]
        if self.quenyan_keyfile:
            args.extend(["--key", self.quenyan_keyfile])
        elif self.quenyan_passphrase:
            args.extend(["--passphrase", self.quenyan_passphrase])
        else:
            raise SystemExit(
                "Provide --quenyan-keyfile or --quenyan-passphrase to encode project"
            )
        _run_quenyan(args, Path.cwd())


__all__ = ["build_py"]
