from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def temp_workspace() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "inputs").mkdir()
        (root / "out").mkdir()
        yield root
