"""Run the read-back API server (build-plan Step 5.1).

Serves JSON shaped to ``docs/design-system.md`` over ``127.0.0.1`` from the span store the
collector writes. Reads are isolated (read-only connections), so it is safe to run while
the collector is writing.

Usage:
    uv run python -m timekeeper.api [--store PATH] [--host 127.0.0.1] [--port 8765]
    (``--store`` defaults to the durable XDG store path shared with the collector.)

Then, e.g.:
    curl -s 127.0.0.1:8765/api/summary?range=today | python -m json.tool
"""

from __future__ import annotations

import argparse

from timekeeper.api.server import _DEFAULT_HOST, _DEFAULT_PORT, serve
from timekeeper.storage.paths import default_store_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TimeKeeper read-back API (Phase 5)")
    parser.add_argument(
        "--store",
        metavar="PATH",
        help="span store SQLite file (default: the durable XDG store path)",
    )
    parser.add_argument("--host", default=_DEFAULT_HOST, help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help="bind port (default 8765)")
    args = parser.parse_args(argv)

    store = args.store or str(default_store_path())
    server = serve(store, host=args.host, port=args.port)
    host, port = server.server_address[:2]
    print(f"read-back API on http://{host}:{port}  (store={store}). Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
