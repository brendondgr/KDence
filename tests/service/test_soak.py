"""Step 7.2 (headless) -- the leak-detection math, without the multi-hour run.

The full-day soak is a human's judgement over real use; the slope/flat verdict underneath it
is deterministic and tested here against synthetic flat and climbing RSS series.
"""

from __future__ import annotations

from kdence.service import soak

HOUR = 3600.0
MIB = 1024 * 1024


def _series(start_rss: int, growth_per_hour: int, hours: float, step_s: float = 60.0):
    """A synthetic RSS series growing linearly at ``growth_per_hour`` bytes/hour."""
    samples = []
    t = 0.0
    while t <= hours * HOUR:
        rss = int(start_rss + growth_per_hour * (t / HOUR))
        samples.append(soak.Sample(t=t, rss_bytes=rss))
        t += step_s
    return samples


def test_flat_series_reads_flat() -> None:
    summary = soak.summarize(_series(40 * MIB, growth_per_hour=0, hours=8))
    assert summary.flat is True
    assert abs(summary.slope_bytes_per_hour) < 1024  # ~0 bytes/hour
    assert summary.rss_min == summary.rss_max == 40 * MIB


def test_steadily_climbing_series_is_flagged() -> None:
    # 20 MiB/hour is well past the 5 MiB/hour tolerance -> a real leak.
    summary = soak.summarize(_series(40 * MIB, growth_per_hour=20 * MIB, hours=8))
    assert summary.flat is False
    assert summary.slope_bytes_per_hour == __import__("pytest").approx(20 * MIB, rel=0.05)
    assert summary.rss_last > summary.rss_min


def test_slow_growth_within_tolerance_stays_flat() -> None:
    # 1 MiB/hour of allocator jitter should not trip the alarm.
    summary = soak.summarize(_series(40 * MIB, growth_per_hour=1 * MIB, hours=8))
    assert summary.flat is True


def test_downward_slope_is_never_a_leak() -> None:
    summary = soak.summarize(_series(80 * MIB, growth_per_hour=-10 * MIB, hours=4))
    assert summary.flat is True
    assert summary.slope_bytes_per_hour < 0


def test_empty_and_single_sample_are_inconclusive_not_crashes() -> None:
    empty = soak.summarize([])
    assert empty.samples == 0 and empty.flat is True
    one = soak.summarize([soak.Sample(t=0.0, rss_bytes=42 * MIB)])
    assert one.samples == 1 and one.flat is True
    assert one.rss_last == 42 * MIB


def test_summary_is_json_serializable() -> None:
    import json

    summary = soak.summarize(_series(40 * MIB, growth_per_hour=0, hours=1))
    json.dumps(summary.as_dict())  # must not raise
