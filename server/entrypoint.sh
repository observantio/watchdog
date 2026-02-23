#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
	if [ -n "${BECERTAIN_ANALYZE_STORAGE_PATH:-}" ]; then
		mkdir -p "${BECERTAIN_ANALYZE_STORAGE_PATH}"
		chown -R appuser:appuser "${BECERTAIN_ANALYZE_STORAGE_PATH}"
	fi
	exec gosu appuser "$@"
fi

exec "$@"
