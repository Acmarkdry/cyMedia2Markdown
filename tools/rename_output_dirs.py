# -*- coding: utf-8 -*-
"""Rename generated output directories from source ids to readable titles."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from video_manifest import make_unique_slug, safe_output_name


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_outputs() -> list[Path]:
    if not OUTPUT_ROOT.exists():
        return []
    return sorted(
        path
        for path in OUTPUT_ROOT.iterdir()
        if path.is_dir() and (path / "status.json").exists()
    )


def assert_output_child(path: Path) -> None:
    resolved = path.resolve()
    output_resolved = OUTPUT_ROOT.resolve()
    if output_resolved not in resolved.parents:
        raise RuntimeError(f"Refusing to move path outside output/: {resolved}")


def proposed_moves(paths: list[Path]) -> list[tuple[Path, Path, dict]]:
    seen = {path.name for path in paths}
    moves = []
    for path in paths:
        status_path = path / "status.json"
        status = load_json(status_path)
        title = str(status.get("title") or (status.get("media") or {}).get("title") or path.name)
        source_id = str(status.get("source_id") or status.get("slug") or path.name)
        target_name = make_unique_slug(safe_output_name(title, source_id), seen - {path.name})
        if target_name == path.name:
            continue
        moves.append((path, OUTPUT_ROOT / target_name, status))
        seen.add(target_name)
    return moves


def rename_outputs(dry_run: bool) -> list[dict]:
    paths = iter_outputs()
    moves = proposed_moves(paths)
    results = []
    for source, target, status in moves:
        assert_output_child(source)
        assert_output_child(target)
        if target.exists():
            raise RuntimeError(f"Target already exists: {target}")
        payload = {
            "from": source.name,
            "to": target.name,
            "title": status.get("title"),
            "dry_run": dry_run,
        }
        if not dry_run:
            old_slug = status.get("slug") or source.name
            status["source_id"] = status.get("source_id") or old_slug
            status["legacy_slug"] = old_slug
            status["slug"] = target.name
            status["out_dir"] = str(target)
            write_json(source / "status.json", status)
            shutil.move(str(source), str(target))
        results.append(payload)
    return results


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Rename output folders to readable video titles.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for item in rename_outputs(args.dry_run):
        print(json.dumps({"stage": "rename", **item}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
