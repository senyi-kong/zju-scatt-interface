#!/usr/bin/env bash
set -euo pipefail
example_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
example_python="${PYTHON:-python}"
"$example_python" "$example_dir/local_environment.py"
cd -- "$example_dir"
if [[ "$#" -eq 0 ]]; then
    set -- 01_database_overview.py --offline
fi
exec "$example_python" "$@"
