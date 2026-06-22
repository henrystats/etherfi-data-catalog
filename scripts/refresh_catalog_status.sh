#!/bin/zsh

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: scripts/refresh_catalog_status.sh path/to/tracker.csv" >&2
  exit 1
fi

csv_path="$1"

if [ ! -f "$csv_path" ]; then
  echo "CSV file not found: $csv_path" >&2
  exit 1
fi

.venv/bin/python scripts/update_freshness_from_tracker.py "$csv_path"

echo "Catalog status refreshed successfully."
echo "Generated runtime file: status/dataset_freshness.yaml"
