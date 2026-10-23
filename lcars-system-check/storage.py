"""Save local diagnostic reports."""

import json
from datetime import datetime, timezone
from pathlib import Path


def save_report(content: str | list[dict], folder: str | Path, suffix: str) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = folder / f"report_{stamp}.{suffix}"
    if suffix == "json":
        path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(str(content), encoding="utf-8")
    return path
