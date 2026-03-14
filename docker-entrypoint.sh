#!/bin/sh
set -e

PROCESS_TYPE="${PROCESS_TYPE:-web}"

case "$PROCESS_TYPE" in
  worker)
    echo "Starting worker process..."
    exec python -m app.worker.run
    ;;
  web)
    echo "Starting web process..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
    ;;
  *)
    echo "Unknown PROCESS_TYPE: $PROCESS_TYPE (expected 'web' or 'worker')" >&2
    exit 1
    ;;
esac
