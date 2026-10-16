#!/usr/bin/env bash
set -Eeuo pipefail
PIN=81d2f9e9aa231fa3467c190e88e6c94fb76ccaa7
ROOT="$PWD"
mkdir -p output
git clone --filter=blob:none https://github.com/xradens/kernel_xiaomi_surya.git riwutos11-susfs-probe
cd riwutos11-susfs-probe
git fetch --depth 1 origin "$PIN"
git checkout --detach "$PIN"
curl -fL --retry 3 -o "$ROOT/output/susfs-4.14.patch" "https://raw.githubusercontent.com/ShirkNeko/susfs4ksu/master/kernel_patches/50_add_susfs_in_kernel-4.14.patch"
set +e
git apply --check "$ROOT/output/susfs-4.14.patch" > "$ROOT/output/susfs-patch-check.log" 2>&1
RC=$?
set -e
if [ "$RC" -eq 0 ]; then
  echo "SUSFS 4.14 patch applies cleanly to pinned XRadens source (not integrated or boot-tested)" | tee "$ROOT/output/susfs-patch-status.txt"
else
  echo "SUSFS 4.14 patch does not apply cleanly; port required. DO NOT FLASH." | tee "$ROOT/output/susfs-patch-status.txt"
fi
cat "$ROOT/output/susfs-patch-check.log"
echo "Result code: $RC"


# Compare another independent 4.14 backport without modifying kernel source.
curl -fL --retry 3 -o "$ROOT/output/susfs-4.14-backport.patch" "https://raw.githubusercontent.com/devnoname120/susfs4ksu-toco/kernel-4.14-backport/kernel_patches/50_add_susfs_in_kernel-4.14.patch"
set +e
git apply --check "$ROOT/output/susfs-4.14-backport.patch" > "$ROOT/output/susfs-backport-check.log" 2>&1
BACKPORT_RC=$?
set -e
if [ "$BACKPORT_RC" -eq 0 ]; then
  echo 'Alternative 4.14 backport applies cleanly (NOT integrated)' | tee "$ROOT/output/susfs-backport-status.txt"
else
  echo 'Alternative 4.14 backport needs adaptation (NOT integrated)' | tee "$ROOT/output/susfs-backport-status.txt"
fi
cat "$ROOT/output/susfs-backport-check.log"
echo "Backport result code: $BACKPORT_RC"

# Isolated partial application: preserve clean hunks and capture only rejected sections.
mkdir -p "$ROOT/output/susfs-partial-rejects"
set +e
git apply --reject --whitespace=nowarn "$ROOT/output/susfs-4.14-backport.patch" > "$ROOT/output/susfs-partial-apply.log" 2>&1
PARTIAL_RC=$?
set -e
find . -name '*.rej' -type f | while read -r file; do
  dst="$ROOT/output/susfs-partial-rejects/${file#./}"
  mkdir -p "$(dirname "$dst")"
  cp "$file" "$dst"
done
printf 'Partial apply status: %s\\n' "$PARTIAL_RC" > "$ROOT/output/susfs-partial-status.txt"
find "$ROOT/output/susfs-partial-rejects" -type f | sort >> "$ROOT/output/susfs-partial-status.txt"
echo 'PARTIAL PATCH IS DIAGNOSTIC ONLY. DO NOT FLASH.' >> "$ROOT/output/susfs-partial-status.txt"

# Print only remaining rejected hunks plus local source context for precise porting.
for target in fs/proc/cmdline.c fs/proc/task_mmu.c; do
  echo "===== REJECT: $target ====="
  if [ -f "$target.rej" ]; then cat "$target.rej"; else echo "No reject file"; fi
  echo "===== SOURCE CONTEXT: $target ====="
  case "$target" in
    fs/proc/cmdline.c) nl -ba "$target" | sed -n '35,125p' ;;
    fs/proc/task_mmu.c) nl -ba "$target" | sed -n '390,530p' ;;
  esac
done

# Adapt only the two rejected hunks to the pinned XRadens 4.14 source.
python3 - <<'PY'
from pathlib import Path
p=Path('fs/proc/cmdline.c')
s=p.read_text()
anchor='static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n'
assert s.count(anchor)==1
assert 'susfs_spoof_cmdline_or_bootconfig' not in s
s=s.replace(anchor, '''#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
extern int susfs_spoof_cmdline_or_bootconfig(struct seq_file *m);
#endif
'''+anchor+'''#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
\tif (!susfs_spoof_cmdline_or_bootconfig(m)) {
\t\tseq_putc(m, '\\n');
\t\treturn 0;
\t}
#endif
''')
p.write_text(s)
p=Path('fs/proc/task_mmu.c')
s=p.read_text()
anchor='static void\nshow_map_vma(struct seq_file *m, struct vm_area_struct *vma, int is_pid)'
assert s.count(anchor)==1
assert 'extern void susfs_sus_ino_for_show_map_vma' not in s
s=s.replace(anchor, '''#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
extern void susfs_sus_ino_for_show_map_vma(unsigned long ino, dev_t *out_dev, unsigned long *out_ino);
#endif

'''+anchor)
p.write_text(s)
print('Adapted two rejected SUSFS declaration/cmdline hunks')
PY
# Check source-level integration only; not a boot or KernelSU API validation.
python3 - <<'PY'
from pathlib import Path
assert 'susfs_spoof_cmdline_or_bootconfig(m)' in Path('fs/proc/cmdline.c').read_text()
assert 'extern void susfs_sus_ino_for_show_map_vma' in Path('fs/proc/task_mmu.c').read_text()
for p in ('fs/susfs.c','include/linux/susfs.h'):
    print(p, 'exists:', Path(p).exists())
print('SUSFS SOURCE PORT STAGED FOR COMPILE TEST; NOT FLASHABLE')
PY

# Stage the two required SUSFS core files from the matching 4.14 backport.
SUSFS_URL="https://raw.githubusercontent.com/devnoname120/susfs4ksu-toco/kernel-4.14-backport/kernel_patches"
mkdir -p fs include/linux
curl -fL --retry 3 -o fs/susfs.c "$SUSFS_URL/fs/susfs.c"
curl -fL --retry 3 -o include/linux/susfs.h "$SUSFS_URL/include/linux/susfs.h"
test -s fs/susfs.c && test -s include/linux/susfs.h
grep -q 'susfs_' fs/susfs.c
grep -q 'susfs_' include/linux/susfs.h
printf 'Core SUSFS files present; compile/integration NOT YET TESTED\\n' > "$ROOT/output/susfs-core-status.txt"
wc -c fs/susfs.c include/linux/susfs.h | tee -a "$ROOT/output/susfs-core-status.txt"
# Rejected patch diagnostic can leave malformed/whitespace contexts; capture instead of aborting.
set +e
git diff --check > "$ROOT/output/susfs-diff-check.txt" 2>&1
DIFF_RC=$?
set -e
printf 'git diff --check exit code: %s\\n' "$DIFF_RC" >> "$ROOT/output/susfs-core-status.txt"
cat "$ROOT/output/susfs-diff-check.txt"
echo 'Source acquisition verified; not yet a compiled SUSFS kernel.'

# Normalize only newly introduced whitespace in patched namespace lines and audit build wiring.
python3 - <<'PY'
from pathlib import Path
p=Path('fs/namespace.c')
s=p.read_text()
s='\n'.join(line.rstrip(' \t') for line in s.split('\n'))
p.write_text(s)
print('Normalized whitespace in fs/namespace.c for SUSFS source staging')
for p in ('fs/Makefile','fs/Kconfig','drivers/kernelsu/Kbuild','drivers/kernelsu/Kconfig'):
    f=Path(p)
    if f.exists():
        txt=f.read_text()
        print(p, 'SUSFS mentions:',txt.count('SUSFS'),'susfs.c build target:', 'susfs.o' in txt)
print('STAGING ONLY: not integrated with KernelSU and not boot-tested')
PY
git diff --check > "$ROOT/output/susfs-diff-check-after-cleanup.txt" 2>&1 || true
cat "$ROOT/output/susfs-diff-check-after-cleanup.txt"

# Locate actual SUSFS Kconfig ownership: upstream patch targets KernelSU Kconfig, not fs/Kconfig.
python3 - <<'PY'
from pathlib import Path
out=Path('../output/susfs-kconfig-audit.txt')
source=Path('../output/susfs-ksu-backport.patch')
import urllib.request
url='https://raw.githubusercontent.com/devnoname120/susfs4ksu-toco/kernel-4.14-backport/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch'
source.write_bytes(urllib.request.urlopen(url,timeout=45).read())
txt=source.read_text()
checks={'kernel_susfs_Kconfig_patch': 'config KSU_SUSFS' in txt,
        'kernel_susfs_Makefile_patch': 'diff --git a/kernel/Makefile' in txt,
        'fs_susfs_target': 'obj-$(CONFIG_KSU_SUSFS) += susfs.o' in Path('fs/Makefile').read_text()}
out.write_text('\n'.join(f'{k}: {v}' for k,v in checks.items())+
               '\nSUSFS KernelSU patch is NOT yet applied.\n')
print(out.read_text())
assert all(checks.values())
PY

# Probe SUSFS KernelSU patch independently against the actual KernelSU Next legacy branch.
git clone --depth 1 --branch legacy https://github.com/KernelSU-Next/KernelSU-Next.git "$ROOT/riwutos11-ksunext-probe"
cd "$ROOT/riwutos11-ksunext-probe/kernel"
set +e
git apply --check "$ROOT/output/susfs-ksu-backport.patch" > "$ROOT/output/susfs-ksu-compat.log" 2>&1
KSU_PATCH_RC=$?
set -e
echo "KernelSU Next legacy SUSFS patch compatibility exit code: $KSU_PATCH_RC" | tee "$ROOT/output/susfs-ksu-compat-status.txt"
cat "$ROOT/output/susfs-ksu-compat.log"
echo "PROBE ONLY: no KernelSU integration or boot validation" >> "$ROOT/output/susfs-ksu-compat-status.txt"

# Verify the artifact exists before layout comparison and use a stable absolute path.
test -s "$ROOT/output/susfs-ksu-backport.patch" || { echo 'Missing SUSFS patch in output folder' >&2; exit 7; }
export SUSFS_PROBE_ROOT="$ROOT"
# Analyze patch layout versus KernelSU Next without applying incompatible old KernelSU code.
python3 - <<'PY'
from pathlib import Path
import re, os
outdir=Path(os.environ['SUSFS_PROBE_ROOT'])/'output'
patch=(outdir/'susfs-ksu-backport.patch').read_text()
target=Path('.')
paths=re.findall(r'^diff --git a/(\S+) b/',patch,re.M)
with (outdir/'susfs-ksu-layout-map.txt').open('w') as out:
    for p in paths:
        # kernel/ is the upstream patch root, while this checkout is already at kernel/
        rel=p.removeprefix('kernel/')
        exists=(target/rel).exists()
        print(f'{rel}: {"PRESENT" if exists else "MISSING"}',file=out)
    print('Old KernelSU patch is not applied to KernelSU Next.',file=out)
print((outdir/'susfs-ksu-layout-map.txt').read_text())
PY

# Resolve relocated KernelSU Next subsystems, avoiding a blind legacy patch.
python3 - <<'PY'
from pathlib import Path
import os
outdir=Path(os.environ['SUSFS_PROBE_ROOT'])/'output'
mappings={
 'allowlist.c':'policy/allowlist.c',
 'apk_sign.c':'manager/apk_sign.c',
 'apk_sign.h':'manager/apk_sign.h',
 'kernel_compat.c':'compat/kernel_compat.c',
 'kernel_compat.h':'compat/kernel_compat.h',
 'ksud.c':'runtime/ksud_integration.c',
 'manager.h':'manager/apk_sign.h',
 'sucompat.c':'feature/sucompat.c',
 'throne_tracker.c':'manager/throne_tracker.c',
 'throne_tracker.h':'manager/throne_tracker.h',
 'core_hook.c':'hook/hook_manager.c',
 'ksu.c':'core/init.c',
}
with (outdir/'susfs-ksu-relocation-map.txt').open('w') as out:
    for old,new in mappings.items():
        print(f'{old} -> {new}: {"EXISTS" if Path(new).is_file() else "MISSING"}',file=out)
    print('These paths are candidates only, not API-compatible patch targets.',file=out)
print((outdir/'susfs-ksu-relocation-map.txt').read_text())
PY
