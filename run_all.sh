#!/usr/bin/env bash
# One-command launcher: starts the FastAPI backend and the Streamlit UI together.
# Each server is detached with nohup, so they keep running after this window
# closes. Idempotent — safe to re-run when both are already up.
#
# Usage:  wsl -d Ubuntu-26.04 -- bash ./run_all.sh
set -e

PROJ="/mnt/c/Users/kunta/OneDrive/Documents/crop pest detection"
cd "$PROJ"
source .venv/bin/activate

echo "== Crop Pest & Disease Detector =="

# ---- 1) FastAPI backend on :8000 ----------------------------------------
if curl -fsS -m 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo "[ok] API already running on :8000"
else
  echo "[..] starting API on :8000 ..."
  nohup ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    > .freebuff/api-8000.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS -m 2 http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
    sleep 1
  done
  if curl -fsS -m 2 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "[ok] API up"
  else
    echo "[err] API failed to start — see .freebuff/api-8000.log"
    exit 1
  fi
fi

# ---- 2) Streamlit UI on :8501 -------------------------------------------
if curl -fsS -m 3 http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
  echo "[ok] Streamlit already running on :8501"
else
  echo "[..] starting Streamlit on :8501 ..."
  nohup ./.venv/bin/streamlit run streamlit_app.py \
    --server.port 8501 --server.address 127.0.0.1 --server.headless true \
    > .freebuff/streamlit-8501.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -fsS -m 2 http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1 && break
    sleep 1
  done
  if curl -fsS -m 2 http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
    echo "[ok] Streamlit up"
  else
    echo "[err] Streamlit failed to start — see .freebuff/streamlit-8501.log"
    exit 1
  fi
fi

echo
echo "  UI:   http://127.0.0.1:8501"
echo "  API:  http://127.0.0.1:8000/docs"
echo "  (servers run in the background — close this window and they keep going)"
