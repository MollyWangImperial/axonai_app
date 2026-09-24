"""Split the private Molly cue bundle into Render-sized secret files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MAX_SECRET_BYTES = 500 * 1024


def split_bundle(source: Path) -> tuple[Path, Path]:
    content = json.loads(source.read_text(encoding="ascii"))
    if content.get("version") != 1 or content.get("voice") != "Molly" or not isinstance(content.get("entries"), dict):
        raise ValueError("Invalid Molly cue bundle")
    parts: list[dict[str, str]] = [{}, {}]
    for key, audio in sorted(content["entries"].items(), key=lambda item: (-len(item[1]), item[0])):
        part = min(parts, key=lambda entries: sum(len(value) for value in entries.values()))
        part[key] = audio
    outputs = tuple(source.with_name(f"reach-molly-bundle-{index}.json") for index in (1, 2))
    for output, entries in zip(outputs, parts):
        data = json.dumps({"version": 1, "voice": "Molly", "entries": entries}, separators=(",", ":"))
        if len(data) >= MAX_SECRET_BYTES:
            raise ValueError(f"{output.name} exceeds Render's 500 KiB secret-file limit")
        output.write_text(data, encoding="ascii")
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    for path in split_bundle(parser.parse_args().source):
        print(f"{path}: {path.stat().st_size} bytes")
