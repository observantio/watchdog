#!/bin/sh
set -e

DATA_DIR="${STORAGE_DIR:-/data/beobservant}"

mkdir -p "$DATA_DIR"
chown -R appuser:appuser "$DATA_DIR"

exec gosu appuser "$@"
