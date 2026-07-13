#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAF_ROOT="${VAF_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
VAF_PORT="${VAF_PORT:-8790}"
PYTHON="${PYTHON:-$VAF_ROOT/.venv/bin/python}"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="${VAF_LOG_DIR:-$VAF_ROOT/logs}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "deploy/macos/deploy.sh must run on macOS." >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing venv Python: $PYTHON" >&2
  echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

mkdir -p "$LAUNCH_AGENT_DIR" "$LOG_DIR" "$VAF_ROOT/db" "$VAF_ROOT/data/runs" \
  "$VAF_ROOT/data/01_素材库/对标视频/manual_import"

render_plist() {
  local template="$1"
  local target="$2"
  sed \
    -e "s#__VAF_ROOT__#$VAF_ROOT#g" \
    -e "s#__PYTHON__#$PYTHON#g" \
    -e "s#__VAF_PORT__#$VAF_PORT#g" \
    -e "s#__LOG_DIR__#$LOG_DIR#g" \
    "$template" > "$target"
}

install_agent() {
  local label="$1"
  local template="$2"
  local target="$LAUNCH_AGENT_DIR/$label.plist"
  render_plist "$template" "$target"
  launchctl unload "$target" >/dev/null 2>&1 || true
  launchctl load "$target"
}

install_agent "com.vaf.orchestrator" "$SCRIPT_DIR/com.vaf.orchestrator.plist"
install_agent "com.vaf.worker" "$SCRIPT_DIR/com.vaf.worker.plist"

health_url="http://127.0.0.1:$VAF_PORT/healthz"
for _ in $(seq 1 30); do
  if curl -fsS "$health_url" >/dev/null 2>&1; then
    echo "orchestrator healthy: $health_url"
    break
  fi
  sleep 1
done

if ! curl -fsS "$health_url" >/dev/null 2>&1; then
  echo "orchestrator health check failed: $health_url" >&2
  exit 1
fi

echo "macOS sleep reminder:"
echo "  sudo pmset -a sleep 0"
echo "Use only on a dedicated production Mac, then restore your normal pmset policy later."
