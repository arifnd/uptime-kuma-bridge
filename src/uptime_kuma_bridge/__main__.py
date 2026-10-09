"""Module entry point: ``python -m uptime_kuma_bridge``."""

from __future__ import annotations

from .app import run

__all__ = ["main"]


def main() -> None:
    run()


if __name__ == "__main__":  # pragma: no cover
    main()
