"""Compatibility shim.

Prefer the installed entry point:

    uptime-kuma-bridge
    python -m uptime_kuma_bridge
"""

from __future__ import annotations

from uptime_kuma_bridge.app import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
