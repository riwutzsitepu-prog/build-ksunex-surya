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
