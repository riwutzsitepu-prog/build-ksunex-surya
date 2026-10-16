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
git diff --check > "$ROOT/output/susfs-diff-check.txt" 2>&1
