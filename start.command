#!/bin/sh
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$project_dir/start.sh" "$@"
