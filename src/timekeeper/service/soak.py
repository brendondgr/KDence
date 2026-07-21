"""Pure resource-summary for the long-run soak (build-plan Step 7.2).

Slow leaks and drift only show over hours, so the *verdict* -- "resources flat, numbers pass
the smell test" -- is the human's over a real working day. But the leak-detection math should
be tested, not eyeballed: this module reduces a series of RSS samples to a least-squares slope
and a ``flat`` boolean against a tolerance. No I/O, no clock -- so a synthetic flat series and
a synthetic climbing series can assert the verdict headlessly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# A user daemon that idles most of the day should not grow by more than this per hour.
# Generous: catches a real leak (MBs/hour) without flagging allocator jitter.
DEFAULT_SLOPE_TOLERANCE_BYTES_PER_HOUR = 5 * 1024 * 1024  # 5 MiB/hour

_SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class Sample:
    """One resource observation: wall-clock ``t`` (seconds) and resident set size (bytes)."""

    t: float
    rss_bytes: int


@dataclass(frozen=True)
class SoakSummary:
    samples: int
    duration_seconds: float
    rss_min: int
    rss_max: int
    rss_last: int
    slope_bytes_per_hour: float
    flat: bool
    tolerance_bytes_per_hour: float

    def as_dict(self) -> dict:
        return {
            "samples": self.samples,
            "duration_seconds": self.duration_seconds,
            "rss_min": self.rss_min,
            "rss_max": self.rss_max,
            "rss_last": self.rss_last,
            "slope_bytes_per_hour": self.slope_bytes_per_hour,
            "flat": self.flat,
            "tolerance_bytes_per_hour": self.tolerance_bytes_per_hour,
        }


def _least_squares_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Slope of the best-fit line ``y = a + b*x`` (units: y-per-x). 0.0 if x has no spread."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0.0:  # all samples at the same instant -> undefined trend, call it flat
        return 0.0
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return cov_xy / var_x


def summarize(
    samples: Sequence[Sample],
    tolerance_bytes_per_hour: float = DEFAULT_SLOPE_TOLERANCE_BYTES_PER_HOUR,
) -> SoakSummary:
    """Reduce RSS samples to a slope and a ``flat`` verdict.

    ``flat`` is True when the fitted RSS growth is at or below ``tolerance_bytes_per_hour``.
    A downward slope is always flat (freeing memory is never a leak). Empty or single-sample
    input yields a zero-slope, ``flat=True`` summary rather than raising -- an incomplete soak
    is inconclusive, not a failure.
    """
    if not samples:
        return SoakSummary(
            samples=0,
            duration_seconds=0.0,
            rss_min=0,
            rss_max=0,
            rss_last=0,
            slope_bytes_per_hour=0.0,
            flat=True,
            tolerance_bytes_per_hour=tolerance_bytes_per_hour,
        )

    rss = [s.rss_bytes for s in samples]
    ts = [s.t for s in samples]
    duration = ts[-1] - ts[0]

    slope_per_second = _least_squares_slope(ts, [float(v) for v in rss])
    slope_per_hour = slope_per_second * _SECONDS_PER_HOUR

    return SoakSummary(
        samples=len(samples),
        duration_seconds=duration,
        rss_min=min(rss),
        rss_max=max(rss),
        rss_last=rss[-1],
        slope_bytes_per_hour=slope_per_hour,
        flat=slope_per_hour <= tolerance_bytes_per_hour,
        tolerance_bytes_per_hour=tolerance_bytes_per_hour,
    )
