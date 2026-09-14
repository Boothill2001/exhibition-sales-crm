#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

docker compose \
  --project-directory "$SCRIPT_DIR" \
  --file "$SCRIPT_DIR/compose.yml" \
  down --volumes --remove-orphans
