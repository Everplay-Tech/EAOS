#!/usr/bin/env python3
"""Analyze Roulette Kernel boot logs to classify outcomes and surface next steps."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


@dataclass
class BootObservation:
    run_dir: Path
    exit_code: int
    serial_text: str
    qemu_text: str

    @property
    def classified_phase(self) -> str:
        if "Roulette Kernel" in self.serial_text:
            return "kernel_vga"
        if "Boot" in self.serial_text or "BRK" in self.qemu_text:
            return "bootloader_partial"
        if "Triple fault" in self.qemu_text:
            return "triple_fault"
        if not self.serial_text.strip():
            return "no_serial"
        return "unknown"

    @property
    def suggestions(self) -> list[str]:
        phase = self.classified_phase
        hints: list[str] = []
        if phase == "kernel_vga":
            hints.append("Kernel reached VGA output; verify T9 syscall loop")
        elif phase == "bootloader_partial":
            hints.append("Bootloader ran but kernel entry not observed; inspect segment setup")
        elif phase == "triple_fault":
            hints.append("Triple fault detected; enable serial init earlier")
        elif phase == "no_serial":
            hints.append("Serial log empty; ensure -serial stdio and outb instructions")
        else:
            hints.append("Outcome unknown; review serial/qemu logs manually")
        return hints


def latest_run_dir() -> Optional[Path]:
    if not LOG_DIR.exists():
        return None
    runs = sorted(p for p in LOG_DIR.iterdir() if p.is_dir())
    return runs[-1] if runs else None


def load_observation(run_dir: Path) -> BootObservation:
    meta = json.loads((run_dir / "run.json").read_text())
    serial_text = (run_dir / "serial.log").read_text(errors="replace") if (run_dir / "serial.log").exists() else ""
    qemu_text = (run_dir / "qemu.log").read_text(errors="replace") if (run_dir / "qemu.log").exists() else ""
    return BootObservation(run_dir, meta.get("qemu_exit_code", -1), serial_text, qemu_text)


def summarize(observation: BootObservation) -> dict:
    return {
        "run_dir": str(observation.run_dir),
        "exit_code": observation.exit_code,
        "phase": observation.classified_phase,
        "serial_lines": len(observation.serial_text.splitlines()),
        "qemu_lines": len(observation.qemu_text.splitlines()),
        "suggestions": observation.suggestions,
    }


def main() -> None:
    if len(sys.argv) > 1:
        run_dir = Path(sys.argv[1])
    else:
        run_dir = latest_run_dir()
        if run_dir is None:
            print("No logs yet. Run scripts/run_boot.sh first.")
            sys.exit(1)

    obs = load_observation(run_dir)
    summary = summarize(obs)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
