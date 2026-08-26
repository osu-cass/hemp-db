#!/bin/sh
set -eu

# Migrations run in the dedicated one-shot `migrate` service
# (compose.deploy.yaml), which gates app startup; this entrypoint
# stays a plain exec.
exec "$@"
