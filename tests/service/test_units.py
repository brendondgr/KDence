"""Step 7.1 (headless) -- the systemd unit *content* is correct.

No systemd here: the unit text is generated from explicit inputs and the lifecycle-critical
directives are asserted directly. These are the mistakes that would only surface as a broken
login otherwise -- wrong ordering, no restart, a volatile store, a routable bind.
"""

from __future__ import annotations

import configparser

import pytest

from kdence.service import units


def _ctx(**kw) -> units.UnitContext:
    base = dict(python="/proj/.venv/bin/python", working_dir="/proj")
    base.update(kw)
    return units.UnitContext(**base)


def _parse(text: str) -> configparser.ConfigParser:
    # systemd unit files are INI-like; ConfigParser is close enough to read keys back.
    # interpolation=None so systemd specifiers like ``%h`` are read verbatim, not parsed as %().
    parser = configparser.ConfigParser(strict=False, delimiters=("=",), interpolation=None)
    parser.optionxform = str  # keep directive case (After, WantedBy, ...)
    parser.read_string(text)
    return parser


def test_collector_unit_is_a_well_formed_graphical_session_service() -> None:
    cfg = _parse(units.collector_unit(_ctx()))
    assert cfg["Unit"]["After"] == "graphical-session.target"
    assert cfg["Unit"]["PartOf"] == "graphical-session.target"
    assert cfg["Install"]["WantedBy"] == "graphical-session.target"
    assert cfg["Service"]["Type"] == "simple"
    assert cfg["Service"]["WorkingDirectory"] == "/proj"


def test_collector_restarts_on_failure_with_backoff() -> None:
    cfg = _parse(units.collector_unit(_ctx()))
    assert cfg["Service"]["Restart"] == "on-failure"
    assert int(cfg["Service"]["RestartSec"]) >= 1
    # A hard-failing unit must back off, not loop forever. Start-rate limiting is a [Unit]
    # directive in modern systemd -- asserting the section guards against silent regression.
    assert int(cfg["Unit"]["StartLimitBurst"]) >= 1
    assert int(cfg["Unit"]["StartLimitIntervalSec"]) >= 1


def test_collector_execstart_uses_durable_store_and_real_threshold() -> None:
    exec_line = _parse(units.collector_unit(_ctx()))["Service"]["ExecStart"]
    assert "/proj/.venv/bin/python -m kdence.collector" in exec_line
    # Durable, reboot-surviving store -- NOT the volatile /tmp default.
    assert "--store %h/.local/share/kdence/kdence.db" in exec_line
    assert "/tmp" not in exec_line
    # Production idle threshold (300s), not the demo 5s.
    assert "--threshold 300" in exec_line


def test_titles_are_off_by_default_and_opt_in_only() -> None:
    assert "--titles" not in units.collector_unit(_ctx())
    assert "--titles" in units.collector_unit(_ctx(capture_titles=True))


def test_api_unit_binds_localhost_and_orders_after_the_collector() -> None:
    cfg = _parse(units.api_unit(_ctx()))
    exec_line = cfg["Service"]["ExecStart"]
    assert "-m kdence.api" in exec_line
    # Local-only rule: never a routable bind.
    assert "--host 127.0.0.1" in exec_line
    assert cfg["Unit"]["Wants"] == units.COLLECTOR_SERVICE
    assert units.COLLECTOR_SERVICE in cfg["Unit"]["After"]
    assert "graphical-session.target" in cfg["Unit"]["After"]


def test_api_shares_the_same_durable_store_as_the_collector() -> None:
    api_exec = _parse(units.api_unit(_ctx()))["Service"]["ExecStart"]
    col_exec = _parse(units.collector_unit(_ctx()))["Service"]["ExecStart"]
    store = "--store %h/.local/share/kdence/kdence.db"
    assert store in api_exec and store in col_exec


def test_render_all_returns_both_named_units() -> None:
    rendered = units.render_all(_ctx())
    assert set(rendered) == {units.COLLECTOR_SERVICE, units.API_SERVICE}
    for text in rendered.values():
        assert text.endswith("\n")  # trailing newline, POSIX-clean


@pytest.mark.parametrize("unit_fn", [units.collector_unit, units.api_unit])
def test_units_are_parseable_ini(unit_fn) -> None:
    # If systemd can't parse it, the service never starts -- so it must at least round-trip.
    cfg = _parse(unit_fn(_ctx()))
    assert "Unit" in cfg and "Service" in cfg and "Install" in cfg


# -- browser tab-ingest port (browser-activity / robust-install) --------------


def test_collector_execstart_includes_the_ingest_port() -> None:
    cfg = _parse(units.collector_unit(_ctx()))
    exec_start = cfg["Service"]["ExecStart"]
    assert f"--ingest-port {units.DEFAULT_INGEST_PORT}" in exec_start
    assert units.DEFAULT_INGEST_PORT == 5786  # canonical default


def test_ports_are_overridable_and_default_to_canonical() -> None:
    api = _parse(units.api_unit(_ctx()))
    assert "--port 5785" in api["Service"]["ExecStart"]  # canonical API default
    custom = _parse(units.collector_unit(_ctx(ingest_port=6000)))
    assert "--ingest-port 6000" in custom["Service"]["ExecStart"]
    api_custom = _parse(units.api_unit(_ctx(port=6001)))
    assert "--port 6001" in api_custom["Service"]["ExecStart"]
