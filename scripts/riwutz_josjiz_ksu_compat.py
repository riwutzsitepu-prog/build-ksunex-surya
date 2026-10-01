#!/usr/bin/env python3
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('ksu-next/kernel')

p = root / 'core_hook.c'
s = p.read_text()

marker = 'static bool ksu_module_mounted = false;\n'
susfs_head = '''#ifdef CONFIG_KSU_SUSFS
bool susfs_is_allow_su(void)
{
\tif (ksu_is_manager()) {
\t\treturn true;
\t}
\treturn ksu_is_allow_uid(current_uid().val);
}

extern u32 susfs_zygote_sid;
extern void susfs_run_try_umount_for_current_mnt_ns(void);
extern bool susfs_is_mnt_devname_ksu(struct path *path);
#endif // CONFIG_KSU_SUSFS

'''
if 'bool susfs_is_allow_su(void)' not in s:
    if marker not in s:
        raise SystemExit('core_hook: module_mounted anchor missing')
    s = s.replace(marker, susfs_head + marker, 1)

s = s.replace('extern int handle_sepolicy(', 'extern int ksu_handle_sepolicy(', 1)
s = re.sub(r'(?<![A-Za-z0-9_])is_manager\(\)', 'ksu_is_manager()', s)

mount_anchor = '\tif (is_non_appuid(new_uid)) {\n'
mount_block = '''#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tbool is_zygote_child = susfs_is_sid_equal(old->security, susfs_zygote_sid);
\tif (likely(is_zygote_child)) {
\t\tif (unlikely(new_uid.val < 10000 && new_uid.val >= 1000)) {
\t\t\tstruct path path;
\t\t\tif (!kern_path("/data/adb/susfs_umount_for_zygote_system_process", 0, &path)) {
\t\t\t\tpath_put(&path);
\t\t\t\tgoto out_ksu_try_umount;
\t\t\t}
\t\t}
\t}
#endif

'''
if 'susfs_is_sid_equal(old->security, susfs_zygote_sid)' not in s:
    if mount_anchor not in s:
        raise SystemExit('core_hook: is_non_appuid anchor missing')
    s = s.replace(mount_anchor, mount_block + mount_anchor, 1)

zygote_old = '\tif (!is_zygote(old->security)) {\n'
zygote_new = '''#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tif (!is_zygote_child) {
#else
\tif (!ksu_is_zygote(old->security)) {
#endif
'''
if zygote_old in s:
    s = s.replace(zygote_old, zygote_new, 1)
elif 'if (!ksu_is_zygote(old->security))' not in s and 'if (!is_zygote_child)' not in s:
    raise SystemExit('core_hook: zygote check anchor missing')

s = re.sub(r'(?<![A-Za-z0-9_])try_umount\(', 'ksu_try_umount(', s)

start = '\t// fixme: use `collect_mounts` and `iterate_mount` to iterate all mountpoint and\n'
if '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n\t// susfs comes first' not in s:
    if start not in s:
        raise SystemExit('core_hook: umount block start missing')
    s = s.replace(start,
        '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n'
        '\t// susfs comes first; preserve v1.1.1 isolated-app behavior\n'
        '\tsusfs_try_umount_all(new_uid.val);\n'
        '#else\n' + start, 1)
    end = '\tksu_try_umount("/system/etc/hosts", false, MNT_DETACH);\n\n\t// try umount lsposed dex2oat bins\n'
    if end not in s:
        raise SystemExit('core_hook: umount block end missing')
    s = s.replace(end,
        '\tksu_try_umount("/system/etc/hosts", false, MNT_DETACH);\n'
        '#endif\n\n'
        '\t// try umount lsposed dex2oat bins\n', 1)

for token in (
    'bool susfs_is_allow_su(void)',
    'extern int ksu_handle_sepolicy(',
    'susfs_is_sid_equal(old->security, susfs_zygote_sid)',
    'out_ksu_try_umount:',
    'susfs_try_umount_all(new_uid.val);',
    'ksu_try_umount("/system", true, 0);',
):
    if token not in s:
        raise SystemExit(f'core_hook compatibility token missing: {token}')
p.write_text(s)

p = root / 'selinux/rules.c'
s = p.read_text()
s = s.replace('void apply_kernelsu_rules()', 'void ksu_apply_kernelsu_rules()', 1)
s = s.replace('int handle_sepolicy(', 'int ksu_handle_sepolicy(', 1)
s = re.sub(r'(?<![A-Za-z0-9_])getenforce\(\)', 'ksu_getenforce()', s)

if 'susfs_set_zygote_sid();' not in s:
    anchor = '\tmutex_unlock(&ksu_rules);\n'
    block = '''#ifdef CONFIG_KSU_SUSFS
\tksu_allow(db, "zygote", "labeledfs", "filesystem", "unmount");
\tsusfs_set_init_sid();
\tsusfs_set_ksu_sid();
\tsusfs_set_zygote_sid();
#endif

'''
    if anchor not in s:
        raise SystemExit('selinux rules: mutex_unlock anchor missing')
    s = s.replace(anchor, block + anchor, 1)

for token in (
    'void ksu_apply_kernelsu_rules()',
    'int ksu_handle_sepolicy(',
    'ksu_getenforce()',
    'susfs_set_init_sid();',
    'susfs_set_ksu_sid();',
    'susfs_set_zygote_sid();',
):
    if token not in s:
        raise SystemExit(f'selinux rules compatibility token missing: {token}')
p.write_text(s)

p = root / 'Makefile'
s = p.read_text()
start = s.find('# .git is a text file')
end = s.find('ifeq ($(shell grep -q " current_sid(void)"', start)
if start < 0 or end < 0:
    raise SystemExit('Could not locate KSU version block')
forced = ('KSU_VERSION := 12851\n'
          '$(info -- KernelSU-Next version: $(KSU_VERSION))\n'
          'ccflags-y += -DKSU_VERSION=$(KSU_VERSION)\n\n')
p.write_text(s[:start] + forced + s[end:])

for rel in ('Kconfig', 'selinux/selinux.c', 'sucompat.c'):
    p = root / rel
    lines = [line.rstrip() for line in p.read_text().splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    p.write_text('\n'.join(lines) + '\n')
