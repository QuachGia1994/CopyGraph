from __future__ import annotations

import json
from collections.abc import Mapping


def safe_json_for_html(report: Mapping[str, object]) -> str:
    rendered = json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return rendered.replace("<", "\\u003c").replace("&", "\\u0026")
