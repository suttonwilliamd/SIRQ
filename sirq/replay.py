from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .core import Observation


def read_jsonl(path: str | Path) -> Iterator[Observation]:
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
            yield Observation.from_dict(payload.get("observation", payload))


def replay(path: str | Path, runtime) -> list:
    return runtime.process_many(read_jsonl(path))
