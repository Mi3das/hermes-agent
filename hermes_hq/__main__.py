"""HERMES HQ launcher.

    python -m hermes_hq            # start on http://127.0.0.1:8787
    python -m hermes_hq --port 9000 --provider anthropic --model claude-opus-4-8
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="hermes_hq", description="HERMES HQ -- visual multi-agent command center"
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--provider", default=None, help="override HQ Commander provider")
    p.add_argument("--model", default=None, help="override HQ Commander model")
    args = p.parse_args(argv)

    try:
        import uvicorn
    except Exception:  # pragma: no cover
        print("uvicorn is required: pip install uvicorn", file=sys.stderr)
        return 1

    from hermes_hq.server import create_app

    app = create_app(provider=args.provider, model=args.model)
    print("\n  ╔══════════════════════════════════════════╗")
    print("  ║            H E R M E S   H Q             ║")
    print("  ║   autonomous multi-agent command center  ║")
    print("  ╚══════════════════════════════════════════╝")
    print(f"\n  → open  http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
