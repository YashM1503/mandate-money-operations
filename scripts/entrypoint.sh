#!/bin/sh
set -eu
exec uvicorn mandate.api:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --no-proxy-headers
