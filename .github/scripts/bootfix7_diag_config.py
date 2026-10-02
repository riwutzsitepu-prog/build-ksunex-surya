#!/usr/bin/env python3
from pathlib import Path
import hashlib, sys

repo = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
kernel = Path(sys.argv[2] if len(sys.argv) > 2 else 'kernel')
out = kernel / 'outdiag'

parts = [
    repo / '.github/configs/wih-riwut-a10-delta.part00',
    repo / '.github/configs/wih-riwut-a10-delta.part01a',
    repo / '.github/configs/wih-riwut-a10-delta.part01b',
    repo / '.github/configs/wih-riwut-a10-delta.part02',
    repo / '.github/configs/wih-riwut-a10-delta.part03',
]
delta = b''.join(p.read_bytes() for p in parts)
expected = '1692159dfb98bb4889e5bd9e2ffb07ee604936eeb30f37420e4cda4286d25105'
actual = hashlib.sha256(delta).hexdigest()
if actual != expected:
    raise SystemExit(f'delta SHA mismatch: {actual}')
(repo / 'wih-riwut-a10-delta.config').write_bytes(delta)

cfg = out / '.config'
lines = cfg.read_text().splitlines()
pos = {}
for i, line in enumerate(lines):
    if line.startswith('CONFIG_') and '=' in line:
        pos[line.split('=', 1)[0]] = i
    elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
        pos[line.split()[1]] = i

for raw in delta.decode().splitlines():
    line = raw.strip()
    if not line:
        continue
    if line.startswith('CONFIG_') and '=' in line:
        key = line.split('=', 1)[0]
    elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
        key = line.split()[1]
    else:
        continue
    if key in pos:
        lines[pos[key]] = line
    else:
        pos[key] = len(lines)
        lines.append(line)
cfg.write_text('\n'.join(lines) + '\n')
print(f'A10 delta merged: {len(delta)} bytes, SHA256 {actual}')
