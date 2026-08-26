"""Disposable research-session lifecycle."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ResearchSession:
    root: Path
    closed: bool = False

    @classmethod
    def create(cls, parent: Path | None = None) -> "ResearchSession":
        if parent is not None:
            parent.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(prefix="researcheus-", dir=parent))
        (path / "working").mkdir()
        (path / "preview").mkdir()
        return cls(path)

    @property
    def working(self) -> Path:
        return self.root / "working"

    @property
    def preview(self) -> Path:
        return self.root / "preview"

    def cleanup(self) -> None:
        if not self.closed:
            shutil.rmtree(self.root, ignore_errors=True)
            self.closed = True

