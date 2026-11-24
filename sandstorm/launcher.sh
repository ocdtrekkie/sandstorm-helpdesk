#!/bin/sh
set -eu
cd /opt/helpdesk
export HELPDESK_DATA_DIR=/var/helpdesk
export HELPDESK_DEV_MODE=0
export PORT=8000
export PYTHONDONTWRITEBYTECODE=1
umask 077
exec /opt/helpdesk-env/bin/python /opt/helpdesk/run.py
