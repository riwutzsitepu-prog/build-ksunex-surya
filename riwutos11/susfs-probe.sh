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
curl -fL --retry 3 -o include/linux/susfs_def.h "$SUSFS_URL/include/linux/susfs_def.h"
test -s fs/susfs.c && test -s include/linux/susfs.h && test -s include/linux/susfs_def.h
grep -q 'susfs_' fs/susfs.c
grep -q 'susfs_' include/linux/susfs.h
printf 'Core SUSFS files present; compile/integration NOT YET TESTED\\n' > "$ROOT/output/susfs-core-status.txt"
wc -c fs/susfs.c include/linux/susfs.h include/linux/susfs_def.h | tee -a "$ROOT/output/susfs-core-status.txt"
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

# Audit relocated interfaces in actual KernelSU Next files; do not apply old patch blindly.
python3 - <<'PY'
from pathlib import Path
import os,re
outdir=Path(os.environ['SUSFS_PROBE_ROOT'])/'output'
needles={'policy/allowlist.c':['is_uid_allowed','allowlist'],
'feature/sucompat.c':['ksu_handle_execve','ksu_handle_faccessat'],
'runtime/ksud_integration.c':['ksud','boot'],
'hook/hook_manager.c':['ksu_handle_setresuid','syscall'],
'core/init.c':['ksu','init'],
'selinux/selinux.c':['susfs','selinux']}
with (outdir/'susfs-ksu-api-audit.txt').open('w') as out:
    for filename,terms in needles.items():
        source=Path(filename).read_text()
        print(filename,file=out)
        for term in terms:
            print(f'  {term}: {len(re.findall(re.escape(term),source))} occurrences',file=out)
    print('STATIC INSPECTION ONLY; SUSFS NOT COMPILED OR ENABLED',file=out)
print((outdir/'susfs-ksu-api-audit.txt').read_text())
PY

# Stage only the SUSFS Kconfig switch in the disposable KernelSU Next checkout.
# This is NOT the full legacy SUSFS patch and cannot enable SUSFS functionality.
python3 - <<'PY'
from pathlib import Path
import os
p=Path('Kconfig')
s=p.read_text()
assert s.rstrip().endswith('endmenu'), 'KernelSU Kconfig layout changed'
assert 'config KSU_SUSFS' not in s, 'SUSFS already defined; stop rather than duplicate'
anchor='\nendmenu'
addition='''
config KSU_SUSFS
    bool "KernelSU SUSFS compatibility (experimental)"
    depends on KSU
    default n
    help
      Select SUSFS integration after porting its KernelSU hooks.
      Keep disabled until the integration build passes.

config KSU_SUSFS_SPOOF_UNAME
    bool "SUSFS uname hook isolated compile probe"
    depends on KSU_SUSFS
    default n

config KSU_SUSFS_SUS_MOUNT
    bool "SUSFS mount feature isolated compile probe"
    depends on KSU_SUSFS
    default n
'''
pos=s.rfind(anchor)
s=s[:pos]+'\n'+addition+s[pos:]
p.write_text(s)
out=Path(os.environ['SUSFS_PROBE_ROOT'])/'output'/'susfs-ksu-kconfig-stage.txt'
out.write_text('KSU_SUSFS Kconfig entry staged in disposable KernelSU clone; default n; no SUSFS integration or boot validation.\n')
print(out.read_text())
PY

# Validate the staged SUSFS option using the kernel's real Kconfig parser.
# This remains a disposable source tree, and SUSFS is not enabled for boot.
cp -a "$ROOT/riwutos11-ksunext-probe/kernel" "$ROOT/riwutos11-susfs-probe/drivers/kernelsu" 2>/dev/null || true
cd "$ROOT/riwutos11-susfs-probe"
python3 - <<'PY'
from pathlib import Path
p=Path('drivers/Kconfig')
s=p.read_text()
line='source "drivers/kernelsu/Kconfig"'
if line not in s:
    s+='\n'+line+'\n'
    p.write_text(s)
p=Path('drivers/Makefile')
s=p.read_text()
line='obj-$(CONFIG_KSU) += kernelsu/'
if line not in s:
    s+='\n'+line+'\n'
    p.write_text(s)
p=Path('arch/arm64/configs/surya_defconfig')
s=p.read_text()+'\nCONFIG_KSU=y\n# CONFIG_KSU_SUSFS is not set\n'
p.write_text(s)
PY
set +e
make O="$ROOT/output/susfs-config-obj" ARCH=arm64 surya_defconfig > "$ROOT/output/susfs-config-test.log" 2>&1
CFG_RC=$?
set -e
echo "KernelSU/SUSFS Kconfig parser exit code: $CFG_RC" | tee "$ROOT/output/susfs-config-test-status.txt"
if [ "$CFG_RC" -eq 0 ]; then
  grep -E '^CONFIG_KSU=|^# CONFIG_KSU_SUSFS' "$ROOT/output/susfs-config-obj/.config" | tee -a "$ROOT/output/susfs-config-test-status.txt" || true
else
  tail -n 35 "$ROOT/output/susfs-config-test.log"
fi
echo 'CONFIG TEST ONLY. SUSFS NOT ENABLED OR BOOT TESTED.' >> "$ROOT/output/susfs-config-test-status.txt"

# Second isolated Kconfig pass with SUSFS selected, and a compile preflight.
# This does not alter the primary kernel build or produce a flashable image.
cd "$ROOT/riwutos11-susfs-probe"
sed -i '/^# CONFIG_KSU_SUSFS is not set/d' arch/arm64/configs/surya_defconfig
printf '\nCONFIG_KSU_SUSFS=y\nCONFIG_KSU_SUSFS_SPOOF_UNAME=y\nCONFIG_KSU_SUSFS_SUS_MOUNT=y\n' >> arch/arm64/configs/surya_defconfig
set +e
make O="$ROOT/output/susfs-enabled-obj" ARCH=arm64 surya_defconfig > "$ROOT/output/susfs-enabled-config.log" 2>&1
ENABLED_RC=$?
set -e
printf 'SUSFS enabled config result: %s\n' "$ENABLED_RC" | tee "$ROOT/output/susfs-enabled-status.txt"
if [ "$ENABLED_RC" -eq 0 ]; then
  grep -E '^CONFIG_KSU=|^CONFIG_KSU_SUSFS=|^# CONFIG_KSU_SUSFS' "$ROOT/output/susfs-enabled-obj/.config" | tee -a "$ROOT/output/susfs-enabled-status.txt" || true
fi
echo 'Configuration validation only, not compiled or boot-tested.' >> "$ROOT/output/susfs-enabled-status.txt"

# Compile only SUSFS object to expose source integration errors, no full rebuild.
cd "$ROOT/riwutos11-susfs-probe"
set +e
make -j2 O="$ROOT/output/susfs-enabled-obj" ARCH=arm64 CC=clang LD=ld.lld CROSS_COMPILE=aarch64-linux-gnu- fs/susfs.o > "$ROOT/output/susfs-object-build.log" 2>&1
OBJ_RC=$?
set -e
printf 'SUSFS object compile exit code: %s\n' "$OBJ_RC" | tee "$ROOT/output/susfs-object-status.txt"
if [ "$OBJ_RC" -eq 0 ]; then
  test -s "$ROOT/output/susfs-enabled-obj/fs/susfs.o" || { echo 'Object missing despite successful make' >&2; exit 8; }
  echo 'SUSFS OBJECT COMPILED, BUT NO LINK OR BOOT VALIDATION' >> "$ROOT/output/susfs-object-status.txt"
else
  grep -m 15 -E '(fatal error:|error:|No rule to make target)' "$ROOT/output/susfs-object-build.log" | tee -a "$ROOT/output/susfs-object-status.txt" || true
fi

# Expose compiler failure context in Actions output (not just downloadable artifacts).
echo '===== SUSFS FIRST COMPILER DIAGNOSTICS ====='
grep -n -m 8 -B 5 -A 9 -E '(fatal error:|error:|No rule to make target)' "$ROOT/output/susfs-object-build.log" || tail -n 55 "$ROOT/output/susfs-object-build.log"

# Inspect unresolved symbols in the successfully compiled SUSFS object.
# This does not assert a full kernel link or working KernelSU SUSFS handlers.
if [ -s "$ROOT/output/susfs-enabled-obj/fs/susfs.o" ]; then
  llvm-nm -u "$ROOT/output/susfs-enabled-obj/fs/susfs.o" > "$ROOT/output/susfs-undefined-symbols.txt"
  printf 'SUSFS undefined-symbol audit: %s external references\n' "$(wc -l < "$ROOT/output/susfs-undefined-symbols.txt")" | tee "$ROOT/output/susfs-link-preflight-status.txt"
  grep -E '(susfs|ksu)' "$ROOT/output/susfs-undefined-symbols.txt" | tee -a "$ROOT/output/susfs-link-preflight-status.txt" || true
  echo 'EXTERNAL SYMBOL INVENTORY ONLY; FULL KERNEL LINK NOT TESTED.' >> "$ROOT/output/susfs-link-preflight-status.txt"
else
  echo 'SUSFS object unavailable; cannot audit unresolved symbols' > "$ROOT/output/susfs-link-preflight-status.txt"
fi

# Confirm that the object contains actual SUSFS implementation, not an empty stub.
OBJ="$ROOT/output/susfs-enabled-obj/fs/susfs.o"
REPORT="$ROOT/output/susfs-object-content-audit.txt"
{
  echo "Object byte size: $(wc -c < "$OBJ")"
  echo "All symbols: $(llvm-nm "$OBJ" | wc -l)"
  echo "Defined global symbols: $(llvm-nm --defined-only --extern-only "$OBJ" | wc -l)"
  echo "Undefined symbols: $(llvm-nm -u "$OBJ" | wc -l)"
  echo 'Sample exported SUSFS functions:'
  llvm-nm --defined-only --extern-only "$OBJ" | grep -m 20 -i susfs || true
  echo 'Object sections:'
  llvm-objdump -h "$OBJ" | head -n 30
  echo 'Selected SUSFS feature options:'
  grep -E '^(CONFIG_KSU_SUSFS|# CONFIG_KSU_SUSFS)' "$ROOT/output/susfs-enabled-obj/.config" || true
  echo 'AUDIT ONLY; full kernel linking and on-device boot remain untested.'
} | tee "$REPORT"
