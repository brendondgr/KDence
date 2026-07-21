# Phase 0.1 — Platform Notes

Recorded during Phase 1 execution on **2026-07-20**. These are the facts later steps rely on.

## Session & compositor

| Fact | Value | How observed |
| --- | --- | --- |
| Session type | **Wayland** (not X11 fallback) | `XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY=wayland-0` |
| Desktop | **KDE** | `XDG_CURRENT_DESKTOP=KDE` |
| Plasma version | **6.7.3** | `plasmashell --version` |
| KWin version | **6.7.3** | `kwin --version` |
| Wayland socket | `/run/user/1000/wayland-0` | `ls $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY` |
| DBus session bus | `unix:path=/run/user/1000/bus` | `DBUS_SESSION_BUS_ADDRESS` |

**Statement of certainty:** this is **Wayland, Plasma 6.x** — Step 0.1 gate satisfied.

## Idle-source investigation (feeds Phase 1)

The idle signal source was probed directly rather than assumed:

- **DBus has no idle-time counter on Wayland.**
  `org.freedesktop.ScreenSaver.GetSessionIdleTime` →
  `org.freedesktop.DBus.Error.NotSupported: GetSessionIdleTime is not supported on this platform`.
  So the classic "read an idle-milliseconds counter" approach (works on X11 via KIdleTime)
  is **unavailable here**.

- **The compositor advertises idle protocols** (via `wayland-info`):
  - `ext_idle_notifier_v1` — **version 2** ← the modern standard we use.
  - `org_kde_kwin_idle` — version 1 (legacy KDE equivalent; not used).
  - `zwp_idle_inhibit_manager_v1` — version 1 (inhibitors; not used).

- **Consequence for design:** `ext_idle_notifier_v1` is *event-based*, not a counter. You
  create an `ext_idle_notification_v1` with a timeout; the compositor sends `idled` after
  that much seat inactivity and `resumed` on the next input. There is **no unit to trust and
  no counter to poll** — we time the idle span ourselves with `time.monotonic()` and
  back-date the idle start by the timeout. This is why `ActivityMonitor` owns the threshold
  in pure Python.

## Tooling notes

- Only `dbus-send` is present (no `qdbus`/`qdbus6`).
- `wayland-info` is available and was used to list advertised globals.
- `pywayland` was evaluated and **rejected**: it builds a CFFI extension requiring
  `python3-devel` (`pyconfig.h`) and `wayland-devel`/`libffi-devel` — a `sudo` install and a
  compiler on every machine. The idle client is instead hand-written against the Wayland wire
  protocol using only the standard library. Vendored spec:
  [docs/references/protocols/ext-idle-notify-v1.xml](../references/protocols/ext-idle-notify-v1.xml).
