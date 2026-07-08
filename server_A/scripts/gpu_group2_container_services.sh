#!/bin/bash
# group2 GPU 容器内：检查 / 启动 HAJIMI A 端 + OmniParser（nohup，无 tmux 依赖）
set -euo pipefail

HAJIMI_ROOT="${HAJIMI_ROOT:-/workspace/code/HAJIMI_UI}"
OMNI_VENV="${OMNI_VENV:-/workspace/code/omniparser_api/.venv}"
OMNI_SERVER="/workspace/code/OmniParser/omnitool/omniparserserver"
LOG_DIR="${HAJIMI_ROOT}/logs"
mkdir -p "$LOG_DIR"

probe_omni() {
  curl -sf -m 5 http://127.0.0.1:8002/probe/
}

probe_a() {
  curl -sf -m 5 http://127.0.0.1:8010/api/demo/health
}

start_omni() {
  if probe_omni >/dev/null 2>&1; then
    echo "[OmniParser] already up"
    probe_omni && echo
    return 0
  fi
  pkill -f "omniparserserver.*--port 8002" 2>/dev/null || true
  sleep 1
  cd "${OMNI_SERVER}"
  nohup bash -lc "source ${OMNI_VENV}/bin/activate && python -m omniparserserver \
    --som_model_path ../../weights/icon_detect/model.pt \
    --caption_model_name florence2 \
    --caption_model_path ../../weights/icon_caption_florence \
    --device cuda --host 127.0.0.1 --port 8002" \
    > "${LOG_DIR}/omniparser.log" 2>&1 &
  echo "[OmniParser] starting (log: ${LOG_DIR}/omniparser.log)..."
  for i in $(seq 1 60); do
    if probe_omni >/dev/null 2>&1; then
      echo "[OmniParser] ready after ${i}s"
      probe_omni && echo
      return 0
    fi
    sleep 5
  done
  echo "[OmniParser] not ready after 300s — tail ${LOG_DIR}/omniparser.log"
  tail -30 "${LOG_DIR}/omniparser.log" || true
  return 1
}

start_a() {
  if probe_a >/dev/null 2>&1; then
    echo "[A-end] already up"
    probe_a && echo
    return 0
  fi
  if [[ ! -d "${HAJIMI_ROOT}/server/.venv" ]]; then
    echo "[A-end] missing server/.venv"
    return 1
  fi
  if [[ ! -f "${HAJIMI_ROOT}/server/.env" ]]; then
    echo "[A-end] missing server/.env"
    return 1
  fi
  pkill -f "uvicorn server.main:app.*8010" 2>/dev/null || true
  sleep 1
  cd "${HAJIMI_ROOT}"
  nohup bash -lc "source server/.venv/bin/activate && python -m uvicorn server.main:app --host 0.0.0.0 --port 8010" \
    > "${LOG_DIR}/a_end.log" 2>&1 &
  echo "[A-end] starting (log: ${LOG_DIR}/a_end.log)..."
  for i in $(seq 1 30); do
    if probe_a >/dev/null 2>&1; then
      echo "[A-end] ready after ${i}s"
      probe_a && echo
      return 0
    fi
    sleep 2
  done
  echo "[A-end] not ready — tail ${LOG_DIR}/a_end.log"
  tail -30 "${LOG_DIR}/a_end.log" || true
  return 1
}

case "${1:-status}" in
  status)
    echo "=== OmniParser ==="
    (probe_omni && echo) 2>/dev/null || echo DOWN
    echo "=== A-end ==="
    (probe_a && echo) 2>/dev/null || echo DOWN
    ;;
  start-omni) start_omni ;;
  start-a) start_a ;;
  start-all)
    start_omni
    start_a
    ;;
  *)
    echo "Usage: $0 {status|start-omni|start-a|start-all}"
    exit 1
    ;;
esac
