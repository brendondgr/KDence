"""Pure systemd **user**-unit renderers (build-plan Step 7.1).

The *content* of a unit file is where lifecycle mistakes hide: wrong ordering starts the
collector before DBus is up; a missing ``Restart`` lets it die silently; a ``/tmp`` store
loses the archive on reboot; a routable ``--host`` would break the local-only rule. So the
unit text is generated here from explicit inputs and unit-tested headlessly -- no systemd,
no live session. Only *enabling* the units and surviving a real logout/login is a live gate
(see ``docs/plans/phase-7-productionization.md``).

Design choices (rationale in the plan):

- **Interpreter:** the caller passes the project venv interpreter (``.venv/bin/python``) plus
  the project working dir, so the service never invokes ``uv`` at start (no sync/network).
- **Durable store:** the collector writes ``%h/.local/share/timekeeper/tk.db`` -- systemd
  expands ``%h`` to the user's home. This is an *explicit* ``--store``; it deliberately does
  **not** change the collector's default (that persistent-default work is deferred Phase 9).
- **Ordering:** both units run within ``graphical-session.target`` (after the compositor and
  the session DBus). The API orders after the collector but does not hard-require it, so a
  headless collector-only setup is valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

COLLECTOR_SERVICE = "timekeeper-collector.service"
API_SERVICE = "timekeeper-api.service"

# The durable, reboot-surviving store the *service* writes to (systemd expands ``%h``).
# Explicit on the ExecStart line -- not the process default (Phase 9 owns the default).
DEFAULT_STORE = "%h/.local/share/timekeeper/tk.db"

# Real idle threshold for production use (the CLI defaults to a demo-sized 5s).
DEFAULT_THRESHOLD_SECONDS = 300.0

# Local-only bind for the read-back API -- never a routable address.
LOCAL_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Restart policy: recover from a crash, but back off instead of looping forever.
_RESTART = "on-failure"
_RESTART_SEC = 5
_START_LIMIT_INTERVAL = 60
_START_LIMIT_BURST = 5


@dataclass(frozen=True)
class UnitContext:
    """Everything a unit's ``ExecStart`` needs that depends on the install machine."""

    python: str
    """Absolute path to the interpreter (the project venv's ``python``)."""

    working_dir: str
    """Absolute project root, used as ``WorkingDirectory`` so ``-m timekeeper.*`` resolves."""

    store: str = DEFAULT_STORE
    threshold_seconds: float = DEFAULT_THRESHOLD_SECONDS
    host: str = LOCAL_HOST
    port: int = DEFAULT_PORT
    capture_titles: bool = False
    """Off by default -- titles are sensitive (build-plan Step 2.2)."""

    extra_env: dict[str, str] = field(default_factory=dict)


def _render(sections: dict[str, list[tuple[str, str]]]) -> str:
    """Render an ordered ``{section: [(key, value), ...]}`` map to unit-file text."""
    out: list[str] = []
    for name, entries in sections.items():
        out.append(f"[{name}]")
        out.extend(f"{key}={value}" for key, value in entries)
        out.append("")  # blank line between sections
    return "\n".join(out).rstrip() + "\n"


def _common_service_entries(ctx: UnitContext) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = [
        ("Type", "simple"),
        ("WorkingDirectory", ctx.working_dir),
    ]
    entries += [("Environment", f"{k}={v}") for k, v in ctx.extra_env.items()]
    entries += [
        ("Restart", _RESTART),
        ("RestartSec", str(_RESTART_SEC)),
    ]
    return entries


def collector_unit(ctx: UnitContext) -> str:
    """The essential writer: one process, the single-writer SQLite collector.

    Runs within the graphical session (so DBus + the compositor are up), restarts on failure,
    and persists to the durable store.
    """
    exec_parts = [
        ctx.python,
        "-m",
        "timekeeper.collector",
        "--threshold",
        f"{ctx.threshold_seconds:g}",
        "--store",
        ctx.store,
    ]
    if ctx.capture_titles:
        exec_parts.append("--titles")

    return _render(
        {
            "Unit": [
                ("Description", "TimeKeeper activity collector (single writer)"),
                ("Documentation", "file://%h/.local/share/timekeeper"),
                ("After", "graphical-session.target"),
                ("PartOf", "graphical-session.target"),
                # Start-rate limiting lives in [Unit] in modern systemd (moved out of
                # [Service] in v230+); a hard-failing unit backs off instead of looping.
                ("StartLimitIntervalSec", str(_START_LIMIT_INTERVAL)),
                ("StartLimitBurst", str(_START_LIMIT_BURST)),
            ],
            "Service": [
                *_common_service_entries(ctx),
                ("ExecStart", " ".join(exec_parts)),
            ],
            "Install": [
                ("WantedBy", "graphical-session.target"),
            ],
        }
    )


def api_unit(ctx: UnitContext) -> str:
    """The optional reader: read-back API + live view, bound to localhost only.

    Orders after the collector (so the store exists) but only ``Wants`` it -- a headless
    collector-only setup stays valid. Reads are isolated, so this never blocks the writer.
    """
    exec_parts = [
        ctx.python,
        "-m",
        "timekeeper.api",
        "--store",
        ctx.store,
        "--host",
        ctx.host,
        "--port",
        str(ctx.port),
    ]
    return _render(
        {
            "Unit": [
                ("Description", "TimeKeeper read-back API + live view (localhost)"),
                ("After", f"graphical-session.target {COLLECTOR_SERVICE}"),
                ("Wants", COLLECTOR_SERVICE),
                ("PartOf", "graphical-session.target"),
                ("StartLimitIntervalSec", str(_START_LIMIT_INTERVAL)),
                ("StartLimitBurst", str(_START_LIMIT_BURST)),
            ],
            "Service": [
                *_common_service_entries(ctx),
                ("ExecStart", " ".join(exec_parts)),
            ],
            "Install": [
                ("WantedBy", "graphical-session.target"),
            ],
        }
    )


def render_all(ctx: UnitContext) -> dict[str, str]:
    """Map of ``{filename: unit_text}`` for both units."""
    return {
        COLLECTOR_SERVICE: collector_unit(ctx),
        API_SERVICE: api_unit(ctx),
    }
