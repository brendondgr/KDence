"""Step 4.2 (synthetic) -- the pure time-model suite where correctness lives.

No hardware, no SQL: every event carries a fake wall-clock timestamp, so the four honesty
rules are provable deterministically. The build plan names four cases explicitly; each has
a test below, plus edge cases. The back-dating case (b) is the one people get wrong.

See docs/plans/phase-4-time-model-and-storage.md for the written rules.
"""

from __future__ import annotations

from timekeeper.model.timeline import Span, Timeline

# A generous gap so ordinary heartbeats stitch; suspend tests exceed it deliberately.
MAX_GAP = 5.0


def _durations(spans: tuple[Span, ...]) -> list[float]:
    return [round(s.duration, 6) for s in spans]


def _total(spans: tuple[Span, ...]) -> float:
    return round(sum(s.duration for s in spans), 6)


# -- the four named cases from the build plan ---------------------------------


def test_a_continuous_work_records_about_T() -> None:
    # Heartbeats every 2s for 60s in one app, then a clean stop.
    tl = Timeline(max_gap_seconds=MAX_GAP)
    t0 = 1_000.0
    for i in range(31):  # t0 .. t0+60 inclusive
        tl.active(t0 + i * 2, "code")
    tl.stop(t0 + 60)
    assert len(tl.spans) == 1
    assert _total(tl.spans) == 60.0  # ~= T, no more


def test_b_work_then_walk_away_excludes_the_trailing_idle() -> None:
    # Active until last input at t0+100, THEN detected idle much later. The span must end
    # at last input (back-dated), not at detection -- the trailing idle is not active time.
    tl = Timeline(max_gap_seconds=MAX_GAP)
    t0 = 0.0
    for i in range(21):  # heartbeats t0 .. t0+100 (gap 5 == max_gap, still stitches)
        tl.active(t0 + i * 5, "firefox")
    last_input = t0 + 100
    detected_idle_at = t0 + 400  # 5 minutes later, but idle() is passed the back-dated instant
    tl.idle(last_input)
    # A later real-time detection does not extend the span.
    assert _total(tl.spans) == 100.0
    assert tl.spans[-1].end == last_input
    assert tl.spans[-1].end != detected_idle_at
    assert tl.open_span is None  # idle closed it


def test_c_rapid_app_switching_is_contiguous_and_sums() -> None:
    tl = Timeline(max_gap_seconds=MAX_GAP)
    # A(0->2) B(2->3) C(3->7) A(7->10)
    tl.active(0.0, "A")
    tl.active(2.0, "B")
    tl.active(3.0, "C")
    tl.active(7.0, "A")
    tl.stop(10.0)
    spans = tl.spans
    assert [s.app_class for s in spans] == ["A", "B", "C", "A"]
    assert _durations(spans) == [2.0, 1.0, 4.0, 3.0]
    # Contiguous & non-overlapping: each span starts exactly where the last ended.
    for prev, nxt in zip(spans, spans[1:]):  # noqa: B905 -- pairwise, intentionally unequal
        assert nxt.start == prev.end
    assert _total(spans) == 10.0


def test_d_suspend_gap_is_not_phantom_active_time() -> None:
    # Work, then the machine suspends for an hour (no heartbeats), then work resumes.
    tl = Timeline(max_gap_seconds=MAX_GAP)
    tl.active(0.0, "code")
    tl.active(2.0, "code")
    tl.active(4.0, "code")  # first span: [0, 4]
    tl.active(4.0 + 3600, "code")  # an hour later -- gap >> max_gap
    tl.active(4.0 + 3602, "code")  # second span: [4+3600, 4+3602]
    tl.stop(4.0 + 3602)
    spans = tl.spans
    assert len(spans) == 2
    assert _durations(spans) == [4.0, 2.0]
    # The suspended hour is absent -- total is the two real work slices, not ~3600.
    assert _total(spans) == 6.0


# -- edges --------------------------------------------------------------------


def test_idle_when_already_idle_is_a_noop() -> None:
    tl = Timeline(max_gap_seconds=MAX_GAP)
    tl.active(0.0, "code")
    tl.idle(5.0)
    tl.idle(9.0)  # already idle -- must not create or reopen anything
    assert len(tl.spans) == 1
    assert tl.spans[0].end == 5.0


def test_resume_after_idle_starts_a_fresh_span() -> None:
    tl = Timeline(max_gap_seconds=MAX_GAP)
    tl.active(0.0, "code")
    tl.idle(3.0)
    tl.active(300.0, "code")  # came back 5 min later
    tl.stop(305.0)
    spans = tl.spans
    assert _durations(spans) == [3.0, 5.0]
    assert _total(spans) == 8.0  # the away time is not counted


def test_desktop_is_active_but_appless() -> None:
    tl = Timeline(max_gap_seconds=MAX_GAP)
    tl.active(0.0, None)  # bare desktop
    tl.active(2.0, "code")
    tl.stop(3.0)
    spans = tl.spans
    assert spans[0].app_class is None
    assert spans[0].label == "(desktop)"
    assert spans[1].app_class == "code"


def test_title_change_same_app_is_a_new_span_when_titles_captured() -> None:
    # The reporter only emits title changes when capture is on; the model treats a
    # different title as a different window (a genuine document switch).
    tl = Timeline(max_gap_seconds=MAX_GAP)
    tl.active(0.0, "code", "a.py")
    tl.active(2.0, "code", "b.py")
    tl.stop(4.0)
    spans = tl.spans
    assert [s.title for s in spans] == ["a.py", "b.py"]
    assert _durations(spans) == [2.0, 2.0]


def test_callbacks_fire_open_extend_close_in_order() -> None:
    events: list[str] = []
    tl = Timeline(
        max_gap_seconds=MAX_GAP,
        on_open=lambda s: events.append(f"open:{s.app_class}"),
        on_extend=lambda s: events.append(f"extend:{s.end:g}"),
        on_close=lambda s: events.append(f"close:{s.app_class}:{s.end:g}"),
    )
    tl.active(0.0, "A")  # open A
    tl.active(2.0, "A")  # extend to 2
    tl.active(5.0, "B")  # close A@5, open B
    tl.stop(6.0)  # close B@6
    assert events == ["open:A", "extend:2", "close:A:5", "open:B", "close:B:6"]


def test_backwards_wall_clock_jump_does_not_shrink_a_span() -> None:
    tl = Timeline(max_gap_seconds=MAX_GAP)
    tl.active(100.0, "code")
    tl.active(103.0, "code")  # end -> 103
    tl.active(101.0, "code")  # clock jumped back; must not move end backwards
    assert tl.open_span is not None
    assert tl.open_span.end == 103.0


def test_stop_when_idle_is_a_noop() -> None:
    tl = Timeline(max_gap_seconds=MAX_GAP)
    tl.stop(10.0)  # nothing open
    assert tl.spans == ()
