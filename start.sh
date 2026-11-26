#!/bin/sh
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python_bin="$project_dir/.venv/bin/python"
if [ ! -x "$python_bin" ]; then python_bin=python3; fi
exec "$python_bin" "$project_dir/start.py" "$@"
