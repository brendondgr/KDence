#!/usr/bin/env bash
#
# KDence — all-in-one installer.
#
# Downloads (if needed), installs the Python environment, writes the systemd *user*
# units, and enables the collector + read-back API so tracking starts now and on every
# graphical login.
#
# Usage:
#   ./install.sh                        # run from a checkout, or…
#   curl -LsSf <raw-url>/install.sh | bash    # bootstrap from scratch
#
# Override anything via env, e.g.:
#   KD_API_PORT=5785 KD_INGEST_PORT=5786 ./install.sh
#
# Env knobs (all optional):
#   KD_REPO_URL       git URL to clone if not already in a checkout
#                     (default: https://github.com/brendondgr/TimeKeeper-v2.git)
#   KD_INSTALL_DIR    where to clone if bootstrapping (default: ~/.local/share/kdence-src)
#   KD_API_PORT       read-back API + dashboard port (default: 8765, auto-bumped if busy)
#   KD_INGEST_PORT    browser tab-ingest port        (default: 8766, auto-bumped if busy)
#   KD_THRESHOLD      idle threshold seconds          (default: 300)
#   KD_TITLES=1       capture window titles (sensitive; off by default)
#   KD_SKIP_UV_INSTALL=1   do not auto-install uv if it is missing
#   KD_NO_ENABLE=1    write units but do not enable/start them
#
set -euo pipefail

# ---- config ---------------------------------------------------------------
REPO_URL="${KD_REPO_URL:-https://github.com/brendondgr/TimeKeeper-v2.git}"
INSTALL_DIR="${KD_INSTALL_DIR:-$HOME/.local/share/kdence-src}"
API_PORT="${KD_API_PORT:-8765}"
INGEST_PORT="${KD_INGEST_PORT:-8766}"
THRESHOLD="${KD_THRESHOLD:-300}"
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

find_free_port() {  # echo the first free port at or after $1
  local p="$1"
  while port_in_use "$p"; do p=$((p + 1)); done
  printf '%s' "$p"
}

is_kdence_repo() {  # $1 = dir
  [ -f "$1/pyproject.toml" ] && grep -q 'name = "kdence"' "$1/pyproject.toml" 2>/dev/null
}

# ---- 1. preflight ---------------------------------------------------------
say "Checking prerequisites"
have git       || die "git is required."
have systemctl || die "systemctl is required (systemd user session)."
have ss        || warn "'ss' not found — port-conflict detection will be skipped."
systemctl --user show-environment >/dev/null 2>&1 || die "No systemd *user* session (are you in a desktop login?)."

case "${XDG_SESSION_TYPE:-}" in
  wayland) : ;;
  *) warn "Session type is '${XDG_SESSION_TYPE:-unknown}', not 'wayland'. KDence targets KDE Plasma 6 / Wayland; the idle + focus sources may not work otherwise." ;;
esac
[ "${XDG_CURRENT_DESKTOP:-}" = "KDE" ] || warn "Desktop is '${XDG_CURRENT_DESKTOP:-unknown}', not KDE — focus detection relies on KWin scripting."
ok "Base tools present"

# ---- 2. ensure uv ---------------------------------------------------------
if ! have uv; then
  if [ "${KD_SKIP_UV_INSTALL:-}" = "1" ]; then
    die "uv is not installed and KD_SKIP_UV_INSTALL=1. Install it: https://docs.astral.sh/uv/"
  fi
  have curl || die "uv is missing and curl is unavailable to install it."
  say "Installing uv (astral.sh official installer)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # uv lands in ~/.local/bin (or the cargo bin); make it visible to this script.
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  have uv || die "uv install ran but 'uv' is still not on PATH — open a new shell and re-run."
fi
ok "uv: $(uv --version 2>/dev/null || echo present)"

# ---- 3. obtain source -----------------------------------------------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd -P)"
if is_kdence_repo "$SCRIPT_DIR"; then
  SRC_DIR="$SCRIPT_DIR"
  say "Using existing checkout: $SRC_DIR"
elif is_kdence_repo "$PWD"; then
  SRC_DIR="$PWD"
  say "Using existing checkout: $SRC_DIR"
else
  say "Cloning $REPO_URL -> $INSTALL_DIR"
  if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only || warn "Could not fast-forward existing clone; using it as-is."
  else
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
  SRC_DIR="$INSTALL_DIR"
fi
cd "$SRC_DIR"
ok "Source ready at $SRC_DIR"

# ---- 4. install the environment ------------------------------------------
say "Syncing Python 3.13 environment (uv sync)"
uv sync
ok "Environment synced"

# ---- 5. choose ports (auto-avoid conflicts) -------------------------------
if have ss; then
  NEW_API_PORT="$(find_free_port "$API_PORT")"
  [ "$NEW_API_PORT" = "$API_PORT" ] || warn "API port $API_PORT busy -> using $NEW_API_PORT"
  API_PORT="$NEW_API_PORT"

  # keep the ingest port distinct from the API port even after bumping
  [ "$INGEST_PORT" = "$API_PORT" ] && INGEST_PORT=$((INGEST_PORT + 1))
  NEW_INGEST_PORT="$(find_free_port "$INGEST_PORT")"
  [ "$NEW_INGEST_PORT" = "$INGEST_PORT" ] || warn "Ingest port $INGEST_PORT busy -> using $NEW_INGEST_PORT"
  INGEST_PORT="$NEW_INGEST_PORT"
fi
say "Ports: API/dashboard=$API_PORT, tab-ingest=$INGEST_PORT (loopback only)"

# ---- 6. write unit files (via the project's own generator) ----------------
say "Writing systemd user units"
TITLES_FLAG=()
[ "${KD_TITLES:-}" = "1" ] && TITLES_FLAG=(--titles)
uv run python -m kdence.service install "${TITLES_FLAG[@]}" >/dev/null
[ -f "$UNIT_DIR/$COLLECTOR" ] && [ -f "$UNIT_DIR/$API" ] || die "Unit files were not written to $UNIT_DIR"

# ---- 7. patch ports + threshold into the ExecStart lines ------------------
# The generator bakes defaults (8765 API, 8766 ingest); rewrite them to our chosen ports.
# API: replace --port NNNN
sed -i -E "s/--port [0-9]+/--port $API_PORT/" "$UNIT_DIR/$API"
# Collector: set/append --ingest-port, and the idle threshold
if grep -q -- '--ingest-port' "$UNIT_DIR/$COLLECTOR"; then
  sed -i -E "s/--ingest-port [0-9]+/--ingest-port $INGEST_PORT/" "$UNIT_DIR/$COLLECTOR"
else
  sed -i -E "\|kdence\.collector| s|$| --ingest-port $INGEST_PORT|" "$UNIT_DIR/$COLLECTOR"
fi
sed -i -E "s/--threshold [0-9.]+/--threshold $THRESHOLD/" "$UNIT_DIR/$COLLECTOR"
ok "Units written to $UNIT_DIR"

# ---- 8. enable + start ----------------------------------------------------
if [ "${KD_NO_ENABLE:-}" = "1" ]; then
  warn "KD_NO_ENABLE=1 — units written but not enabled. Enable later with:"
  echo "  systemctl --user daemon-reload && systemctl --user enable --now $COLLECTOR $API"
  exit 0
fi

say "Enabling and starting services"
systemctl --user daemon-reload
systemctl --user reset-failed "$COLLECTOR" "$API" 2>/dev/null || true
systemctl --user enable --now "$COLLECTOR"
systemctl --user enable --now "$API"

# ---- 9. verify ------------------------------------------------------------
sleep 2
FAILED=0
for u in "$COLLECTOR" "$API"; do
  if [ "$(systemctl --user is-active "$u")" = "active" ]; then
    ok "$u is active"
  else
    warn "$u is NOT active — check: journalctl --user -u $u -n 30"
    FAILED=1
  fi
done

echo
if [ "$FAILED" = "0" ]; then
  ok "KDence is installed and running."
  echo "   Dashboard:  ${B}http://127.0.0.1:$API_PORT${N}"
  echo "   It will auto-start on every graphical login (systemd user units)."
  echo "   Status:     systemctl --user status $COLLECTOR $API"
  echo "   Logs:       journalctl --user -u $COLLECTOR -f"
  echo "   Uninstall:  systemctl --user disable --now $COLLECTOR $API && uv run python -m kdence.service uninstall"
else
  die "One or more services failed to start — see the hints above."
fi
