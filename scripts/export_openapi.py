"""Export the FastAPI OpenAPI schema to docs/openapi.json."""

from __future__ import annotations

import json
from pathlib import Path

from uptime_kuma_bridge.app import create_app
from uptime_kuma_bridge.config import Settings


def main() -> None:
    settings = Settings(
        uk_username="admin",
        uk_password="admin",
        bridge_allow_anonymous=True,
    )
    app = create_app(settings)
    output = Path("docs/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
