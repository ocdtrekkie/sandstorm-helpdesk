#!/usr/bin/env python3
"""Create a consistent SQLite snapshot, including images. Does not copy sessions."""
import argparse
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('database', type=Path)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
if not args.database.is_file():
    parser.error('Source database does not exist.')
if args.destination.exists():
    parser.error('Destination already exists; refusing to overwrite it.')
args.destination.parent.mkdir(parents=True,exist_ok=True)
source = sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True)
try:
    with args.destination.open('xb'):
        pass
    args.destination.chmod(0o600)
    dest = sqlite3.connect(str(args.destination))
    try:
        source.backup(dest)
        check = dest.execute('PRAGMA integrity_check').fetchone()[0]
        if check != 'ok':
            raise RuntimeError('Backup failed integrity check: '+check)
    finally:
        dest.close()
finally:
    source.close()
print('Backup created and verified.')
