#!/usr/bin/env python3
"""Remove the migrated web-archive-expert from WorkBuddy runtime indexes.

The plugin directory is intentionally retained as a rollback reference. Only
registration/index entries are removed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path


WORKBUDDY = Path(os.environ.get("WORKBUDDY_HOME", Path.home() / ".workbuddy"))
EXPERT_ID = "web-archive-expert"
PATTERNS = {
    "custom_experts": "experts/custom/*/experts.json",
    "marketplace": "plugins/marketplaces/*/.codebuddy-plugin/marketplace.json",
    "recent_experts": "storage/*/global/expert.json",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def remove_registration(key: str, data):
    if key == "custom_experts":
        before = list(data)
        data = [item for item in data if item != EXPERT_ID]
    elif key == "marketplace":
        before = list(data.get("plugins", []))
        data["plugins"] = [
            item for item in data.get("plugins", [])
            if item.get("name") != EXPERT_ID
        ]
    elif key == "recent_experts":
        before = list(data.get("recents", []))
        data["recents"] = [
            item for item in data.get("recents", [])
            if item.get("id") != EXPERT_ID
        ]
    else:
        raise ValueError(key)
    return data, len(before), before


def atomic_write(path: Path, payload) -> None:
    temp = path.with_name(path.name + ".webarchive-migration.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def discover_paths() -> list[tuple[str, Path]]:
    found = []
    for key, pattern in PATTERNS.items():
        for path in sorted(WORKBUDDY.glob(pattern)):
            if path.is_file():
                found.append((key, path))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = WORKBUDDY / "backups" / f"web-archive-migration-{stamp}"
    summary = {}

    paths = discover_paths()
    if not paths:
        print(json.dumps({"status": "no-workbuddy-indexes-found", "root": str(WORKBUDDY)}, indent=2))
        return 0
    for key, path in paths:
        original = load(path)
        baseline = copy.deepcopy(original)
        updated, before_count, _ = remove_registration(key, original)
        after_count = (
            len(updated) if key == "custom_experts"
            else len(updated.get("plugins", [])) if key == "marketplace"
            else len(updated.get("recents", []))
        )
        changed = updated != baseline
        item = {
            "status": "changed" if changed else "already-clean",
            "path": str(path),
            "before": before_count,
            "after": after_count,
        }
        if changed and args.apply:
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / path.name
            backup.write_bytes(path.read_bytes())
            atomic_write(path, updated)
            reread = load(path)
            if reread != updated:
                raise RuntimeError(f"readback mismatch: {path}")
            item["backup"] = str(backup)
        summary[f"{key}:{path}"] = item

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
