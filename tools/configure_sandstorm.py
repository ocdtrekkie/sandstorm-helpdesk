#!/usr/bin/env python3
"""Render the package definition using an app ID owned by the operator."""
import argparse
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('app_id', help='App ID printed by spk keygen; preserve its private key for upgrades')
args = parser.parse_args()
if not re.fullmatch(r'[a-z0-9]{52}',args.app_id):
    parser.error('Expected a 52-character lowercase Sandstorm app ID.')
root = Path(__file__).resolve().parents[1]
output = root/'sandstorm-pkgdef.capnp'
if output.exists():
    parser.error('sandstorm-pkgdef.capnp already exists; move it aside before regenerating.')
source = (root/'sandstorm/sandstorm-pkgdef.capnp.in').read_text()
output.write_text(source.replace('@@APP_ID@@',args.app_id))
print('Created sandstorm-pkgdef.capnp. Next run spk dev in your build environment.')
