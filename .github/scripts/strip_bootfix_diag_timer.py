#!/usr/bin/env python3
from pathlib import Path
import re
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "kernel")
p = root / "init/main.c"
s = p.read_text()

# BOOTFIX7 diagnostic timer was appended only to force a warm panic and collect
# ramoops. BOOTFIX8 baseline must boot normally, so remove the whole diagnostic
# block while keeping PSTORE enabled in the config.
pat = re.compile(
    r'\n\n/\* RIWUTZ BOOTFIX7 diagnostic: force a warm panic after 45 seconds\. \*/\n'
    r'static int riwutz_diag_timeout_thread\(void \*unused\)\n'
    r'\{.*?\n\}\n\n'
    r'static int __init riwutz_diag_timeout_init\(void\)\n'
    r'\{.*?\n\}\n'
    r'core_initcall\(riwutz_diag_timeout_init\);\n',
    re.S,
)

s2, n = pat.subn("\n", s, count=1)
if n != 1:
    raise SystemExit(f"diagnostic timer block removal count={n}, expected 1")

if "RIWUTZ_BOOTFIX7_DIAG_TIMEOUT_45S" in s2 or "riwutz_diag_timeout" in s2:
    raise SystemExit("diagnostic timer marker still present")

p.write_text(s2)
print("BOOTFIX8 baseline: 45s diagnostic panic timer REMOVED")
