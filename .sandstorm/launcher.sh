#!/bin/bash
set -euo pipefail
VENV=/opt/app-venv

cd /opt/app
export HELPDESK_DATA_DIR=/var/helpdesk
export HELPDESK_DEV_MODE=0
export PORT=8000
$VENV/bin/python3 /opt/app/run.py

exit 0
