#!/usr/bin/env python3
"""把后端 OpenAPI 契约导出到 docs/openapi.json（契约单源，入库）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402

OUTPUT = ROOT / "docs" / "openapi.json"


def main() -> None:
    spec = create_app().openapi()
    OUTPUT.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
