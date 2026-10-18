#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(pwd)"
OUT="$ROOT/output"
mkdir -p "$OUT"
echo 'NOT FLASHABLE - diagnostic build only; no SUSFS or boot validation' > "$OUT/STATUS.txt"
trap 'echo "BUILD FAILED at line $LINENO" >&2' ERR
PIN=81d2f9e9aa231fa3467c190e88e6c94fb76ccaa7
git clone --filter=blob:none https://github.com/xradens/kernel_xiaomi_surya.git "$ROOT/riwutos11-source"
cd "$ROOT/riwutos11-source"
git fetch --depth 1 origin "$PIN"
git checkout --detach "$PIN"
test "$(git rev-parse HEAD)" = "$PIN"
echo "$PIN" > "$OUT/source-commit.txt"
grep -qx 'SUBLEVEL = 355' Makefile
sed -i -E 's/^EXTRAVERSION =.*/EXTRAVERSION =/' Makefile
CFG=arch/arm64/configs/surya_defconfig
test -s "$CFG"
sed -i '/^CONFIG_LOCALVERSION=/d;/^CONFIG_LOCALVERSION_AUTO=/d;/^# CONFIG_LOCALVERSION_AUTO is not set/d;/^CONFIG_KSU=/d;/^CONFIG_KSU_MANUAL_HOOK=/d;/^CONFIG_KPROBES=/d;/^CONFIG_KPROBE_EVENTS=/d' "$CFG"
cat >> "$CFG" <<'CONFIG'
CONFIG_LOCALVERSION="-RiwutOS11"
# CONFIG_LOCALVERSION_AUTO is not set
CONFIG_KPROBES=y
CONFIG_KPROBE_EVENTS=y
CONFIG_KSU=y
CONFIG_KSU_MANUAL_HOOK=y
CONFIG_SDCARD_FS=y
CONFIG
curl -fL --retry 3 -o "$OUT/ksu-setup.sh" https://raw.githubusercontent.com/KernelSU-Next/KernelSU-Next/next/kernel/setup.sh
bash "$OUT/ksu-setup.sh" legacy
python3 - <<'PY'
from pathlib import Path
p=Path('kernel/reboot.c')
s=p.read_text()
needle='SYSCALL_DEFINE4(reboot, int, magic1, int, magic2, unsigned int, cmd,'
assert s.count(needle)==1, 'Unexpected reboot syscall layout'
assert 'ksu_handle_sys_reboot' not in s, 'Reboot hook already present'
s=s.replace(needle, '#ifdef CONFIG_KSU\nextern int ksu_handle_sys_reboot(int magic1, int magic2, unsigned int cmd, void __user **arg);\n#endif\n'+needle,1)
needle2='\t/* We only trust the superuser with rebooting the system. */'
assert s.count(needle2)==1
s=s.replace(needle2, '#ifdef CONFIG_KSU\n\tksu_handle_sys_reboot(magic1, magic2, cmd, &arg);\n#endif\n'+needle2,1)
p.write_text(s)
print('KernelSU reboot manual hook installed')
PY
# Manual KernelSU UID transition hook: run only after successful credentials commit.
python3 - <<'PY'
from pathlib import Path
p=Path('kernel/sys.c')
s=p.read_text()
start=s.index('SYSCALL_DEFINE3(setresuid, uid_t, ruid, uid_t, euid, uid_t, suid)')
end=s.index('\nerror:', start)
block=s[start:end]
old='\treturn commit_creds(new);'
assert block.count(old)==1, 'Unexpected setresuid success path'
assert 'ksu_handle_setresuid' not in block
block=block.replace(old, '''\t{
\t\tuid_t ksu_old_uid = from_kuid_munged(current_user_ns(), old->uid);
\t\tuid_t ksu_new_uid = from_kuid_munged(current_user_ns(), new->uid);
\t\tretval = commit_creds(new);
#ifdef CONFIG_KSU
\t\tif (retval == 0)
\t\t\tksu_handle_setresuid(ksu_old_uid, ksu_new_uid);
#endif
\t\treturn retval;
\t}''', 1)
s=s[:start]+block+s[end:]
s=s.replace('SYSCALL_DEFINE3(setresuid, uid_t, ruid, uid_t, euid, uid_t, suid)', '#ifdef CONFIG_KSU\nextern int ksu_handle_setresuid(uid_t old_uid, uid_t new_uid);\n#endif\nSYSCALL_DEFINE3(setresuid, uid_t, ruid, uid_t, euid, uid_t, suid)',1)
p.write_text(s)
print('KernelSU setresuid manual hook installed')
PY
# Manual execveat hook for legacy 4.14. Both execve and execveat converge here.
# Preserve the previously bootable kernel sources except for this guarded call.
python3 - <<'PY'
from pathlib import Path
p=Path('fs/exec.c')
s=p.read_text()
signature='do_execveat_common(int fd, struct filename *filename,'
assert s.count(signature)==1, 'Unexpected do_execveat_common signature'
assert 'ksu_handle_execveat(' not in s, 'KernelSU execveat hook already present'
prototype='#ifdef CONFIG_KSU\nextern int ksu_handle_execveat(int *fd, struct filename **filename_ptr, void *argv, void *envp, int *flags);\n#endif\n'
assert s.count('static int '+signature)==1, 'Unexpected static function declaration'
s=s.replace('static int '+signature,prototype+'static int '+signature,1)
start=s.index(signature)
anchor='\tif (IS_ERR(filename))\n\t\treturn PTR_ERR(filename);\n'
idx=s.index(anchor,start)
s=s[:idx+len(anchor)]+'''
#ifdef CONFIG_KSU
\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
#endif
'''+s[idx+len(anchor):]
assert s.count('ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);')==1
p.write_text(s)
print('KernelSU legacy 4.14 execve/execveat common path hook installed')
PY
# KernelSU legacy 4.14: use slab allocation and expose kallsyms name limit.
python3 - <<'PY'
from pathlib import Path
p=Path('drivers/kernelsu/supercall/dispatch.c')
s=p.read_text()
assert s.count('kvcalloc(')==2 and s.count('kvfree(')==2, 'Unexpected allocation paths'
s=s.replace('kvcalloc(', 'kcalloc(').replace('kvfree(', 'kfree(')
needle='#include <linux/slab.h>'
assert s.count(needle)==1
s=s.replace(needle,needle+'\n#include <linux/kallsyms.h>',1)
p.write_text(s)
print('KernelSU 4.14 slab and kallsyms compatibility installed')
PY
# Linux 4.14 XRadens does not export path_umount. Use the legacy sys_umount path.
python3 - <<'PY'
from pathlib import Path
p=Path('drivers/kernelsu/feature/kernel_umount.c')
s=p.read_text()
needle='#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0) ||'
assert s.count(needle)==1, 'Unexpected KernelSU unmount layout'
s=s.replace(needle, '#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0) ||',1)
# On this 4.14 source do not select the non-existent backported path_umount.
s=s.replace('defined(KSU_HAS_PATH_UMOUNT)\nextern int path_umount', '(defined(KSU_HAS_PATH_UMOUNT) && LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0))\nextern int path_umount',1)
assert 'defined(KSU_HAS_PATH_UMOUNT) && LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)' in s
s=s.replace('#ifndef KSU_HAS_PATH_UMOUNT\n#include <linux/syscalls.h>\n#endif', '#include <linux/syscalls.h>', 1)
assert '#include <linux/syscalls.h>' in s
p.write_text(s)
print('KernelSU legacy 4.14 umount compatibility applied')
PY
export ARCH=arm64 SUBARCH=arm64 KBUILD_BUILD_USER=riwut KBUILD_BUILD_HOST=RiwutOS11
export CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_ARM32=arm-linux-gnueabihf-
make O="$OUT/obj" CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip surya_defconfig
make O="$OUT/obj" CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip olddefconfig
for k in CONFIG_KSU CONFIG_KSU_MANUAL_HOOK CONFIG_SDCARD_FS CONFIG_CONFIGFS_FS; do
  grep -qx "$k=y" "$OUT/obj/.config" || { echo "Missing $k" >&2; exit 4; }
done
make -j2 O="$OUT/obj" CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip Image.gz
IMG="$OUT/obj/arch/arm64/boot/Image.gz"
test -s "$IMG"
gzip -t "$IMG"
gzip -dc "$IMG" | strings > "$OUT/image-strings.txt"
grep -Fq '4.14.355-RiwutOS11' "$OUT/image-strings.txt"
cp "$IMG" "$OUT/Image.gz"
sha256sum "$OUT/Image.gz" > "$OUT/sha256.txt"
# Build device trees separately, without replacing a known-good boot partition.
# Build the confirmed base DTB independently; device overlays remain unvalidated.
make -j2 O="$OUT/obj" CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip qcom/sdmmagpie.dtb
mkdir -p "$OUT/dtb"
find "$OUT/obj/arch/arm64/boot/dts" -type f -name '*.dtb' -exec cp --parents {} "$OUT/dtb/" \;
DTB_COUNT=$(find "$OUT/dtb" -type f -name '*.dtb' | wc -l)
test "$DTB_COUNT" -gt 0 || { echo "No compiled DTBs found" >&2; exit 7; }
printf 'Base DTB files built: %s (overlay DTBO not validated)\n' "$DTB_COUNT" > "$OUT/dtb-status.txt"
find "$OUT/dtb" -type f -name '*.dtb' -print0 | sort -z | xargs -0 sha256sum > "$OUT/dtb-sha256.txt"

# Produce a ROM-independent handoff manifest. No boot partition is modified.
python3 - <<'PY'
from pathlib import Path
import hashlib,json
out=Path('../output')
config=(out/'obj/.config').read_text()
assert '# CONFIG_KSU_SUSFS is not set' in config or 'CONFIG_KSU_SUSFS=' not in config, 'SUSFS unexpectedly enabled'
dtbs=sorted((out/'dtb').rglob('*.dtb'))
assert len(dtbs)==1 and dtbs[0].name=='sdmmagpie.dtb', 'Unexpected DTB set'
def entry(p):
    return {'path':str(p.relative_to(out)), 'bytes':p.stat().st_size,
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
manifest={
 'variant':'RiwutOS11 4.14.355 / Poco X3 NFC surya / no SUSFS',
 'source_commit':(out/'source-commit.txt').read_text().strip(),
 'kernel':entry(out/'Image.gz'),
 'base_dtbs':[entry(p) for p in dtbs],
 'boot_img':'NOT PROVIDED',
 'dtbo_img':'NOT VERIFIED',
 'kernel_su_runtime':'NOT TESTED',
 'ready_to_flash':False
}
(out/'handoff-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Handoff manifest created: NOT FLASHABLE')
PY
# Verify linked KernelSU core symbols, not only CONFIG_KSU in defconfig.
python3 - <<'PY'
from pathlib import Path
out=Path('../output')
sym=(out/'obj/System.map').read_text()
cfg=(out/'obj/.config').read_text()
symbols=('kernelsu_init','ksu_handle_sys_reboot','ksu_handle_setresuid')
checks={name:any(line.split()[-1]==name for line in sym.splitlines() if line.split()) for name in symbols}
checks['CONFIG_KSU_builtin']='CONFIG_KSU=y' in cfg
checks['CONFIG_KSU_MANUAL_HOOK']='CONFIG_KSU_MANUAL_HOOK=y' in cfg
(out/'ksu-link-audit.txt').write_text('KernelSU linked-symbol diagnostic (not a runtime test)\n'+
    ''.join(f'{k}: {v}\n' for k,v in checks.items())+
    'KernelSU manager detection on device: REPORTED NOT INTEGRATED\n')
print((out/'ksu-link-audit.txt').read_text())
PY
# KernelSU initialization evidence from linked image, rather than Kconfig alone.
python3 - <<'PY'
from pathlib import Path
out=Path('../output')
syms=(out/'obj/System.map').read_text().splitlines()
found={line.split()[-1] for line in syms if len(line.split())>=3}
initcalls=sorted(x for x in found if 'kernelsu_init' in x or 'ksu_init' in x)
report=['KernelSU initialization evidence (offline only)',
        'kernelsu_init present: '+str('kernelsu_init' in found),
        'matching initcall symbols: '+(', '.join(initcalls) if initcalls else 'NONE'),
        'initcall linked runtime: NOT TESTED',
        'manager handshake: REPORTED UNSUPPORTED ON DEVICE',
        'su availability: REPORTED MISSING ON DEVICE']
(out/'ksu-initcall-audit.txt').write_text('\n'.join(report)+'\n')
print('\n'.join(report))
PY
# Static readiness audit, independent of compilation success.
python3 - <<'PY'
from pathlib import Path
src=Path('fs/exec.c').read_text()
uid=Path('kernel/sys.c').read_text()
reboot=Path('kernel/reboot.c').read_text()
checks={
  'manual_reboot_hook': 'ksu_handle_sys_reboot(magic1, magic2, cmd, &arg)' in reboot,
  'manual_setresuid_hook': 'ksu_handle_setresuid(ksu_old_uid, ksu_new_uid)' in uid,
  'manual_execve_sucompat_hook': 'ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);' in src,
  'manual_execveat_sucompat_hook': 'ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);' in src,
  'susfs_source': Path('fs/susfs.c').exists(),
}
out=Path('../output/readiness-audit.txt')
out.write_text('RiwutOS11 STATIC READINESS AUDIT\n'+''.join(f'{k}: {v}\n' for k,v in checks.items())+'BOOT TEST: NOT PERFORMED\nREADY TO FLASH: NO\n')
print(out.read_text())
PY

echo 'IMAGE.GZ AND DTBS DIAGNOSTIC ONLY - DTBO AND BOOT IMAGE NOT VALIDATED - NOT FLASHABLE' > "$OUT/STATUS.txt"
