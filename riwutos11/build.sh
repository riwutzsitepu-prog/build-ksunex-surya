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
export ARCH=arm64 SUBARCH=arm64 KBUILD_BUILD_USER=riwut KBUILD_BUILD_HOST=RiwutOS11
export CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_ARM32=arm-linux-gnueabihf-
make O="$OUT/obj" CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip surya_defconfig
make O="$OUT/obj" CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip olddefconfig
for k in CONFIG_KSU CONFIG_KSU_MANUAL_HOOK; do
  grep -qx "$k=y" "$OUT/obj/.config" || { echo "Missing $k" >&2; exit 4; }
done
make -j2 O="$OUT/obj" CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip Image.gz dtbs
IMG="$OUT/obj/arch/arm64/boot/Image.gz"
test -s "$IMG"
gzip -t "$IMG"
gzip -dc "$IMG" | strings > "$OUT/image-strings.txt"
grep -Fq '4.14.355-RiwutOS11' "$OUT/image-strings.txt"
cp "$IMG" "$OUT/Image.gz"
sha256sum "$OUT/Image.gz" > "$OUT/sha256.txt"
echo 'COMPILED ONLY - NOT FLASHABLE - SUSFS and boot validation missing' > "$OUT/STATUS.txt"
