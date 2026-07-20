from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def build_result_report(raw_result: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    return {"result": raw_result, "analysis": analysis}


def write_result_report(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    elif path.suffix.lower() == ".csv":
        points = payload["result"].get("sample_points", [])
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["frequency_ghz", "value_db"])
            writer.writeheader()
            writer.writerows(
                {
                    "frequency_ghz": point.get("frequency_ghz"),
                    "value_db": point.get("value_db"),
                }
                for point in points
            )
    else:
        raise ValueError("Report path must end with .json or .csv.")
    return {"path": str(path), "bytes": path.stat().st_size, "format": path.suffix.lower()[1:]}
