"""Service lifecycle CLI (build-plan Step 7.1 / 7.2).

    uv run python -m kdence.service print                 # dump both units to stdout
    uv run python -m kdence.service install [--titles]    # write units, print enable cmds
    uv run python -m kdence.service uninstall             # remove units, print disable cmds
    uv run python -m kdence.service soak [--interval N] [--out FILE]

``install`` writes the unit files and prints the exact ``systemctl --user`` commands but does
**not** enable them -- enabling a unit is the user's explicit action. ``soak`` samples the two
units' RSS on an interval and, on exit, prints the pure summary from ``soak.summarize`` (the
multi-hour run is the manual gate; the sampler + math are the automatable spine).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from kdence.service import soak as soak_mod
from kdence.service import units


def _project_root() -> str:
    # src/kdence/service/__main__.py -> project root is three parents up from the package.
    return str(Path(__file__).resolve().parents[3])


def _default_ctx(capture_titles: bool = False) -> units.UnitContext:
    return units.UnitContext(
        python=sys.executable,  # the venv interpreter running this install (no uv-at-start)
        working_dir=_project_root(),
        capture_titles=capture_titles,
    )


def _user_unit_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def _cmd_print(_args: argparse.Namespace) -> int:
    for name, text in units.render_all(_default_ctx()).items():
        print(f"# ---- {name} ----")
        print(text)
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    kwargs: dict = {
        "python": sys.executable,  # the venv interpreter running this install (no uv-at-start)
        "working_dir": _project_root(),
        "capture_titles": args.titles,
    }
    if args.api_port is not None:
        kwargs["port"] = args.api_port
    if args.ingest_port is not None:
        kwargs["ingest_port"] = args.ingest_port
    if args.threshold is not None:
        kwargs["threshold_seconds"] = args.threshold
    if args.store:
        kwargs["store"] = args.store
    ctx = units.UnitContext(**kwargs)

    unit_dir = _user_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)

    # Create the durable store's parent dir now so the collector never races to make it (only
    # for the default %h-relative store; an explicit --store may expand systemd specifiers).
    if "%" not in ctx.store:
        Path(ctx.store).expanduser().parent.mkdir(parents=True, exist_ok=True)
    store_parent = Path.home() / ".local" / "share" / "kdence"
    store_parent.mkdir(parents=True, exist_ok=True)

    written = []
    for name, text in units.render_all(ctx).items():
        path = unit_dir / name
        path.write_text(text, encoding="utf-8")
        written.append(path)

    print("Wrote:")
    for path in written:
        print(f"  {path}")
    print(f"\nStore dir ready: {store_parent}")
    print("\nNow enable them (your explicit step):")
    print("  systemctl --user daemon-reload")
    print(f"  systemctl --user enable --now {units.COLLECTOR_SERVICE}")
    print(f"  systemctl --user enable --now {units.API_SERVICE}   # optional (dashboard)")
    print("\nThen verify a full lifecycle: log out and back in, and")
    print(f"  systemctl --user kill {units.COLLECTOR_SERVICE}   # should restart on its own")
    return 0


def _cmd_uninstall(_args: argparse.Namespace) -> int:
    unit_dir = _user_unit_dir()
    for name in (units.COLLECTOR_SERVICE, units.API_SERVICE):
        path = unit_dir / name
        if path.exists():
            path.unlink()
            print(f"Removed {path}")
    print("\nDisable them:")
    print(f"  systemctl --user disable --now {units.COLLECTOR_SERVICE} {units.API_SERVICE}")
    print("  systemctl --user daemon-reload")
    return 0


def _main_pid(unit: str) -> int | None:
    """The unit's MainPID via ``systemctl --user show``; None if not running."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", "-p", "MainPID", "--value", unit],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    pid = int(out) if out.isdigit() else 0
    return pid or None


def _rss_bytes(pid: int) -> int | None:
    """Resident set size from ``/proc/<pid>/status`` (VmRSS, kB) -> bytes."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        return None
    return None


def _cmd_soak(args: argparse.Namespace) -> int:
    monitored = [units.COLLECTOR_SERVICE, units.API_SERVICE]
    out = Path(args.out).open("a", encoding="utf-8") if args.out else None
    per_unit: dict[str, list[soak_mod.Sample]] = {u: [] for u in monitored}
    start = time.time()
    print(f"Sampling RSS every {args.interval:g}s (Ctrl-C to stop and summarize)...")
    try:
        while True:
            now = time.time()
            for unit in monitored:
                pid = _main_pid(unit)
                rss = _rss_bytes(pid) if pid else None
                if rss is not None:
                    per_unit[unit].append(soak_mod.Sample(t=now - start, rss_bytes=rss))
                    row = {"t": round(now - start, 1), "unit": unit, "rss": rss}
                    print(json.dumps(row))
                    if out:
                        out.write(json.dumps(row) + "\n")
                        out.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if out:
            out.close()

    print("\n==== soak summary ====")
    for unit in monitored:
        summary = soak_mod.summarize(per_unit[unit])
        verdict = "FLAT" if summary.flat else "GROWING (investigate)"
        print(f"\n{unit}: {verdict}")
        print(json.dumps(summary.as_dict(), indent=2))
    print("\nThe verdict on totals is yours: do today's numbers match your memory of the day?")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KDence service lifecycle (Phase 7)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("print", help="print both unit files to stdout")

    p_install = sub.add_parser("install", help="write unit files to ~/.config/systemd/user")
    p_install.add_argument(
        "--titles", action="store_true", help="capture window titles (sensitive)"
    )
    p_install.add_argument("--api-port", type=int, help="read-back API/dashboard port")
    p_install.add_argument("--ingest-port", type=int, help="browser tab-ingest port")
    p_install.add_argument("--threshold", type=float, help="idle threshold seconds")
    p_install.add_argument("--store", metavar="PATH", help="span store path (systemd %%h ok)")

    sub.add_parser("uninstall", help="remove the unit files")

    p_soak = sub.add_parser("soak", help="sample unit RSS and summarize on exit")
    p_soak.add_argument("--interval", type=float, default=60.0, help="seconds between samples")
    p_soak.add_argument("--out", metavar="FILE", help="also append samples as JSONL")

    args = parser.parse_args(argv)
    return {
        "print": _cmd_print,
        "install": _cmd_install,
        "uninstall": _cmd_uninstall,
        "soak": _cmd_soak,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
