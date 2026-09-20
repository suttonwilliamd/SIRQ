from __future__ import annotations

import json
import sys
from typing import Iterable, Iterator

from .core import Observation


def stdin_adapter(stream=None) -> Iterator[Observation]:
    stream = stream or sys.stdin
    for line in stream:
        if line.strip():
            yield Observation.from_dict(json.loads(line))


def webhook_payload(payload: dict) -> Observation:
    return Observation.from_dict(payload)


def observations_from_files(paths: Iterable[str]) -> Iterator[Observation]:
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            yield Observation.from_dict(json.load(handle))
