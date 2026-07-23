"""Run the read-back API server (build-plan Step 5.1).

Serves JSON shaped to ``docs/design-system.md`` over ``127.0.0.1`` from the span store the
collector writes. Reads are isolated (read-only connections), so it is safe to run while
the collector is writing.

Usage:
    uv run python -m kdence.api [--store PATH] [--host 127.0.0.1] [--port 5785]
    (``--store`` defaults to the durable XDG store path shared with the collector.)

Then, e.g.:
    curl -s 127.0.0.1:5785/api/summary?range=today | python -m json.tool
"""

from __future__ import annotations

import argparse

from kdence.api.server import _DEFAULT_HOST, _DEFAULT_PORT, serve
from kdence.storage.paths import default_store_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KDence read-back API (Phase 5)")
    parser.add_argument(
        "--store",
        metavar="PATH",
        help="span store SQLite file (default: the durable XDG store path)",
    )
    parser.add_argument("--host", default=_DEFAULT_HOST, help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help="bind port (default 5785)")
    parser.add_argument(
        "--categories",
        metavar="PATH",
        help="category-config JSON file (default: the durable XDG config path)",
    )
    parser.add_argument(
        "--detail",
        metavar="PATH",
        help="in-app detail toggle JSON file (default: the durable XDG config path)",
    )
    args = parser.parse_args(argv)

    store = args.store or str(default_store_path())
    server = serve(
        store,
        host=args.host,
        port=args.port,
        categories_path=args.categories,
        detail_path=args.detail,
    )
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
