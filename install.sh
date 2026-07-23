#!/usr/bin/env bash
#
# KDence — all-in-one installer / restarter.
#
# Reads ./.env (copy it from .env.example), installs the Python environment, generates the
# systemd *user* units from the project's own tested generator, aligns the browser extension
# to the ingest port, and enables + (re)starts the collector + read-back API. Re-run it any
# time to restart with new values — this is the supported way to restart KDence.
#
# Usage:
#   cp .env.example .env && $EDITOR .env      # set your ports etc. (defaults: API 5785, ingest 5786)
#   ./install.sh                              # from a checkout, or…
#   curl -LsSf <raw-url>/install.sh | bash    # bootstrap from scratch
#
# Config comes from ./.env (KDENCE_* keys — see .env.example). A few installer-only knobs are
# still env-overridable: KD_REPO_URL, KD_INSTALL_DIR, KD_SKIP_UV_INSTALL=1, KD_NO_ENABLE=1.
#
set -euo pipefail

# ---- installer-only knobs -------------------------------------------------
REPO_URL="${KD_REPO_URL:-https://github.com/brendondgr/TimeKeeper-v2.git}"
INSTALL_DIR="${KD_INSTALL_DIR:-$HOME/.local/share/kdence-src}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
COLLECTOR="kdence-collector.service"
API="kdence-api.service"

# ---- pretty logging -------------------------------------------------------
if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; N=$'\e[0m'; else B=; G=; Y=; R=; N=; fi
say()  { printf '%s==>%s %s\n' "$B" "$N" "$*"; }
ok()   { printf '%s ok %s %s\n' "$G" "$N" "$*"; }
warn() { printf '%swarn%s %s\n' "$Y" "$N" "$*" >&2; }
die()  { printf '%sfail%s %s\n' "$R" "$N" "$*" >&2; exit 1; }

# ---- helpers --------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }
port_in_use() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1$"; }
is_kdence_repo() { [ -f "$1/pyproject.toml" ] && grep -q 'name = "kdence"' "$1/pyproject.toml" 2>/dev/null; }
truthy() { case "${1:-}" in 1|true|TRUE|True|yes|YES|on|ON) return 0 ;; *) return 1 ;; esac; }

# The pid holding a loopback TCP port, or empty.
port_owner_pid() { ss -ltnpH "sport = :$1" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2; }

# A port we can (re)use only if it is free or already held by our own KDence service. Any other
# owner is a hard error — we never silently bump to a different port (that is what let the
# extension and the collector's ingest silently diverge before).
require_port() {  # $1 port  $2 human label  $3 env-var name to hint
  port_in_use "$1" || { ok "$2 port $1 is free"; return 0; }
  local pid; pid="$(port_owner_pid "$1")"
  if [ -n "$pid" ] && grep -qa 'kdence\.\(api\|collector\)' "/proc/$pid/cmdline" 2>/dev/null; then
    ok "$2 port $1 is held by KDence (will restart)"
  else
    die "$2 port $1 is already in use by another process (pid ${pid:-?}). Change $3 in .env and re-run."
  fi
}

# ---- 1. preflight ---------------------------------------------------------
say "Checking prerequisites"
have git       || die "git is required."
have systemctl || die "systemctl is required (systemd user session)."
have ss        || die "'ss' (iproute2) is required for port checks."
systemctl --user show-environment >/dev/null 2>&1 || die "No systemd *user* session (are you in a desktop login?)."
case "${XDG_SESSION_TYPE:-}" in
  wayland) : ;;
  *) warn "Session type is '${XDG_SESSION_TYPE:-unknown}', not 'wayland'. KDence targets KDE Plasma 6 / Wayland." ;;
esac
[ "${XDG_CURRENT_DESKTOP:-}" = "KDE" ] || warn "Desktop is '${XDG_CURRENT_DESKTOP:-unknown}', not KDE — focus detection relies on KWin scripting."
ok "Base tools present"

# ---- 2. ensure uv ---------------------------------------------------------
if ! have uv; then
  [ "${KD_SKIP_UV_INSTALL:-}" = "1" ] && die "uv is not installed and KD_SKIP_UV_INSTALL=1. See https://docs.astral.sh/uv/"
  have curl || die "uv is missing and curl is unavailable to install it."
  say "Installing uv (astral.sh official installer)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  have uv || die "uv installed but 'uv' is still not on PATH — open a new shell and re-run."
fi
ok "uv: $(uv --version 2>/dev/null || echo present)"

# ---- 3. obtain source -----------------------------------------------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd -P)"
if is_kdence_repo "$SCRIPT_DIR"; then SRC_DIR="$SCRIPT_DIR"
elif is_kdence_repo "$PWD"; then SRC_DIR="$PWD"
else
  say "Cloning $REPO_URL -> $INSTALL_DIR"
  if [ -d "$INSTALL_DIR/.git" ]; then git -C "$INSTALL_DIR" pull --ff-only || warn "Could not fast-forward existing clone; using it as-is."
  else git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"; fi
  SRC_DIR="$INSTALL_DIR"
fi
cd "$SRC_DIR"
ok "Source ready at $SRC_DIR"

# ---- 4. load .env ---------------------------------------------------------
if [ -f "$SRC_DIR/.env" ]; then
  say "Reading configuration from .env"
  set -a; . "$SRC_DIR/.env"; set +a
else
  warn "No .env found — using defaults. Copy .env.example to .env to customise."
fi
API_HOST="${KDENCE_API_HOST:-127.0.0.1}"
API_PORT="${KDENCE_API_PORT:-5785}"
INGEST_PORT="${KDENCE_INGEST_PORT:-5786}"
THRESHOLD="${KDENCE_IDLE_THRESHOLD_SECONDS:-300}"
[ "$API_PORT" = "$INGEST_PORT" ] && die "KDENCE_API_PORT and KDENCE_INGEST_PORT must differ (both $API_PORT)."
say "Ports: API/dashboard=$API_PORT, tab-ingest=$INGEST_PORT (loopback only)"

# ---- 5. verify ports (no silent auto-bump) --------------------------------
require_port "$API_PORT"    "API/dashboard" "KDENCE_API_PORT"
require_port "$INGEST_PORT" "tab-ingest"    "KDENCE_INGEST_PORT"

# ---- 6. install the environment ------------------------------------------
say "Syncing Python 3.13 environment (uv sync)"
uv sync
ok "Environment synced"

# ---- 7. generate + write the unit files (tested generator, no sed) --------
say "Writing systemd user units"
INSTALL_ARGS=(--api-port "$API_PORT" --ingest-port "$INGEST_PORT" --threshold "$THRESHOLD")
truthy "${KDENCE_CAPTURE_TITLES:-}" && INSTALL_ARGS+=(--titles)
[ -n "${KDENCE_DB_PATH:-}" ] && INSTALL_ARGS+=(--store "${KDENCE_DB_PATH/#\~/$HOME}")
# In-app detail providers (opt-in, default OFF) + per-app denylist — see .env.example.
[ -n "${KDENCE_DETAIL_PROVIDERS:-}" ] && INSTALL_ARGS+=(--detail-providers "$KDENCE_DETAIL_PROVIDERS")
[ -n "${KDENCE_DETAIL_DENYLIST:-}" ] && INSTALL_ARGS+=(--detail-denylist "$KDENCE_DETAIL_DENYLIST")
uv run python -m kdence.service install "${INSTALL_ARGS[@]}" >/dev/null
[ -f "$UNIT_DIR/$COLLECTOR" ] && [ -f "$UNIT_DIR/$API" ] || die "Unit files were not written to $UNIT_DIR"
ok "Units written to $UNIT_DIR"

# ---- 8. align the browser extension to the ingest port --------------------
# The extension can't read this env, so bake the ingest port in. Default is 5786, so this is a
# no-op unless you changed the port. Reload the extension afterwards to pick it up.
for f in "$SRC_DIR"/browser-extension/*/tab-reporter.js; do
  [ -f "$f" ] && sed -i -E "s#(http://127\.0\.0\.1:)[0-9]+(/tab)#\1${INGEST_PORT}\2#" "$f"
done
for f in "$SRC_DIR"/browser-extension/*/manifest.json; do
  [ -f "$f" ] && sed -i -E "s#(http://127\.0\.0\.1:)[0-9]+(/\*)#\1${INGEST_PORT}\2#g" "$f"
done
ok "Extension aligned to ingest port $INGEST_PORT"

# ---- 9. enable + (re)start ------------------------------------------------
if [ "${KD_NO_ENABLE:-}" = "1" ]; then
  warn "KD_NO_ENABLE=1 — units written but not enabled. Enable later with:"
  echo "  systemctl --user daemon-reload && systemctl --user enable --now $COLLECTOR $API"
  exit 0
fi
say "Enabling and (re)starting services"
systemctl --user daemon-reload
systemctl --user reset-failed "$COLLECTOR" "$API" 2>/dev/null || true
systemctl --user enable "$COLLECTOR" "$API" >/dev/null 2>&1 || true
systemctl --user restart "$COLLECTOR"
systemctl --user restart "$API"

# ---- 10. verify -----------------------------------------------------------
FAILED=0
for u in "$COLLECTOR" "$API"; do
  if [ "$(systemctl --user is-active "$u")" = "active" ]; then ok "$u is active"
  else warn "$u is NOT active — journalctl --user -u $u -n 30"; FAILED=1; fi
done
if have curl; then
  say "Waiting for the API to answer on $API_HOST:$API_PORT"
  UP=0
  for _ in $(seq 1 20); do curl -fsS "http://$API_HOST:$API_PORT/api/health" >/dev/null 2>&1 && { UP=1; break; }; sleep 0.5; done
  if [ "$UP" = "1" ]; then ok "API healthy at http://$API_HOST:$API_PORT"; else warn "API did not answer /api/health in time."; FAILED=1; fi
fi

echo
[ "$FAILED" = "0" ] || die "One or more services did not come up — see the hints above."
ok "KDence is installed and running."
echo "   Dashboard:  ${B}http://$API_HOST:$API_PORT${N}   (auto-starts on graphical login)"
echo "   Tab-ingest: 127.0.0.1:$INGEST_PORT"
echo "   ${B}Browser extension:${N} (re)load it so it targets the current ingest port ($INGEST_PORT):"
echo "     see ${SRC_DIR}/browser-extension/README.md  — LibreWolf/Firefox: Load Temporary Add-on;"
echo "     Brave/Chromium: Load unpacked. If it was already loaded, click Reload."
echo "   Restart:    re-run ./install.sh   ·   Status: systemctl --user status $COLLECTOR $API"
echo "   Uninstall:  systemctl --user disable --now $COLLECTOR $API && uv run python -m kdence.service uninstall"
