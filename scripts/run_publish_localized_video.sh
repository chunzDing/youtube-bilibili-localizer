#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${SKILL_DIR}/.venv/bin/python"

if [[ -x "${VENV_PYTHON}" ]]; then
  exec "${VENV_PYTHON}" "${SCRIPT_DIR}/publish_localized_video.py" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${SCRIPT_DIR}/publish_localized_video.py" "$@"
fi

echo "Missing Python runtime. Create ${SKILL_DIR}/.venv or install python3." >&2
exit 1
