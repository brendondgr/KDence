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

## Focus-source investigation (feeds Phase 2)

Recorded during Phase 2 execution on **2026-07-21** (same session, Plasma/KWin 6.7.3).
Getting the focused window *out of* KWin on Wayland was probed the same way — proven live,
not assumed (build-plan Step 2.1 gate):

- **KWin scripting is the channel.** The interface is `org.kde.kwin.Scripting` at
  `/Scripting` on `org.kde.KWin` (methods `loadScript(filePath, pluginName) → i`, `start()`,
  `unloadScript(pluginName) → b`, `isScriptLoaded → b`). A loaded script connects to
  `workspace.windowActivated` and reads `workspace.activeWindow`. Window objects expose
  `resourceClass` (app class) and `caption` (title).

- **The signal was renamed in Plasma 6.** It is `workspace.windowActivated(window)` (Plasma 5
  used `clientActivated(client)`). It fires with a **null** window when focus goes to the
  desktop. This is exactly the "renamed between Plasma 5 and 6" hazard Step 0.1 flagged.

- **Egress: `callDBus`, nothing else.** KWin's script engine is sandboxed:
  - `print()` / `console.log` are swallowed unless the `kwin_scripting` logging category is
    enabled (off by default) — confirmed no journal output.
  - `setTimeout` / timers are **not available**.
  - `callDBus(service, path, iface, method, ...args)` **works** and is fire-and-forget. We
    host a private local DBus service (`org.kdence.Focus`) the script calls back into.

- **Verified live:** the script reported the real focused window
  (`class=com.anthropic.Claude, caption=Claude`) to an out-of-compositor Python process, and a
  forced activation reported a **different** identity — a real focus change seen outside the
  compositor. Gate satisfied.

- **Consequence for design:** `focus/` uses `dbus-fast` (pure-Python, no compiler — installs
  cleanly, unlike `pywayland`) to host the receiver and drive KWin scripting. Confirmed the
  Phase 2 stack decision. The script forwards raw `(resourceClass, caption)`; identity and
  title-privacy policy live in the pure `kdence.focus` logic.

## Tooling notes

- Only `dbus-send` is present (no `qdbus`/`qdbus6`); `gdbus` and `busctl` are also available
  and were used to introspect KWin.
- `wayland-info` is available and was used to list advertised globals.
- `pywayland` was evaluated and **rejected**: it builds a CFFI extension requiring
  `python3-devel` (`pyconfig.h`) and `wayland-devel`/`libffi-devel` — a `sudo` install and a
  compiler on every machine. The idle client is instead hand-written against the Wayland wire
  protocol using only the standard library. Vendored spec:
  [docs/references/protocols/ext-idle-notify-v1.xml](../references/protocols/ext-idle-notify-v1.xml).
