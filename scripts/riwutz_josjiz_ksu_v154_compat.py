#!/usr/bin/env python3
from pathlib import Path
import re

root = Path('ksu-next/kernel')

# apk_sign.c: SUSFS v1.5.4 patch expects legacy KSU naming while KSU Next
# v1.1.1 has retry/locking logic. Keep the KSU Next body and expose the
# symbol name expected by the applied SUSFS patch.
p = root / 'apk_sign.c'
s = p.read_text()
s = s.replace('bool is_manager_apk(char *path)', 'bool ksu_is_manager_apk(char *path)', 1)
needle = '\treturn check_v2_signature(path, expected_manager_size, expected_manager_hash);\n}'
if needle in s and '7e0c6d7278a3bb8e364e0fcba95afaf3666cf5ff3c245a3b63c8833bd0445cc4' not in s:
    repl = '''#ifdef CONFIG_KSU_SUSFS
\treturn check_v2_signature(path, expected_manager_size, expected_manager_hash) ||
\t       check_v2_signature(path, 384,
\t\t"7e0c6d7278a3bb8e364e0fcba95afaf3666cf5ff3c245a3b63c8833bd0445cc4");
#else
\treturn check_v2_signature(path, expected_manager_size, expected_manager_hash);
#endif
}'''
    s = s.replace(needle, repl, 1)
if 'bool ksu_is_manager_apk(char *path)' not in s:
    raise SystemExit('apk_sign: manager function anchor missing')
p.write_text(s)

# Make sure header and users are on the same symbol name.
p = root / 'apk_sign.h'
s = p.read_text().replace('bool is_manager_apk(char *path);', 'bool ksu_is_manager_apk(char *path);')
p.write_text(s)
p = root / 'throne_tracker.c'
s = p.read_text()
s = re.sub(r'(?<![A-Za-z0-9_])is_manager_apk\(', 'ksu_is_manager_apk(', s)
p.write_text(s)

# core_hook.c: repair only hunks that conflict with KSU Next v1.1.1.
p = root / 'core_hook.c'
s = p.read_text()
if '#include <linux/susfs.h>' not in s:
    anchor = '#include <linux/mount.h>\n'
    if anchor not in s:
        raise SystemExit('core_hook: mount include anchor missing')
    s = s.replace(anchor, anchor + '\n#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs.h>\n#endif\n', 1)

marker = 'static bool ksu_module_mounted = false;\n'
if 'bool susfs_is_allow_su(void)' not in s:
    if marker not in s:
        raise SystemExit('core_hook: module_mounted anchor missing')
    head = '''#ifdef CONFIG_KSU_SUSFS
bool susfs_is_allow_su(void)
{
\tif (ksu_is_manager())
\t\treturn true;
\treturn ksu_is_allow_uid(current_uid().val);
}

extern u32 susfs_zygote_sid;
extern bool susfs_is_mnt_devname_ksu(struct path *path);
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
extern void susfs_run_try_umount_for_current_mnt_ns(void);
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
static bool susfs_is_umount_for_zygote_system_process_enabled;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
extern bool susfs_is_auto_add_sus_bind_mount_enabled;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
extern bool susfs_is_auto_add_sus_ksu_default_mount_enabled;
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
extern bool susfs_is_auto_add_try_umount_for_bind_mount_enabled;
#endif

static inline void susfs_on_post_fs_data(void)
{
\tstruct path path;
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tif (!kern_path(DATA_ADB_UMOUNT_FOR_ZYGOTE_SYSTEM_PROCESS, 0, &path)) {
\t\tsusfs_is_umount_for_zygote_system_process_enabled = true;
\t\tpath_put(&path);
\t}
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT
\tif (!kern_path(DATA_ADB_NO_AUTO_ADD_SUS_BIND_MOUNT, 0, &path)) {
\t\tsusfs_is_auto_add_sus_bind_mount_enabled = false;
\t\tpath_put(&path);
\t}
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT
\tif (!kern_path(DATA_ADB_NO_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT, 0, &path)) {
\t\tsusfs_is_auto_add_sus_ksu_default_mount_enabled = false;
\t\tpath_put(&path);
\t}
#endif
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
\tif (!kern_path(DATA_ADB_NO_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT, 0, &path)) {
\t\tsusfs_is_auto_add_try_umount_for_bind_mount_enabled = false;
\t\tpath_put(&path);
\t}
#endif
}
#endif

'''
    s = s.replace(marker, head + marker, 1)

s = s.replace('extern int handle_sepolicy(', 'extern int ksu_handle_sepolicy(', 1)
s = re.sub(r'(?<![A-Za-z0-9_])is_manager\(\)', 'ksu_is_manager()', s)
s = re.sub(r'(?<![A-Za-z0-9_])try_umount\(', 'ksu_try_umount(', s)

# KSU Next setuid flow differs from legacy KSU. Preserve its unsupported-app
# handling while adding SUSFS zygote and task-state behavior.
mount_anchor = '\tif (is_non_appuid(new_uid)) {\n'
if 'susfs_is_sid_equal(old->security, susfs_zygote_sid)' not in s:
    block = '''#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tbool is_zygote_child = susfs_is_sid_equal(old->security, susfs_zygote_sid);
\tif (likely(is_zygote_child) &&
\t    unlikely(new_uid.val < 10000 && new_uid.val >= 1000) &&
\t    susfs_is_umount_for_zygote_system_process_enabled)
\t\tgoto out_ksu_try_umount;
#endif

'''
    if mount_anchor not in s:
        raise SystemExit('core_hook: is_non_appuid anchor missing')
    s = s.replace(mount_anchor, block + mount_anchor, 1)

# Mark denied app processes for SUSFS path/kstat filtering.
allow_anchor = '\tif (ksu_is_allow_uid(new_uid.val)) {\n'
if 'current->susfs_task_state |= TASK_STRUCT_NON_ROOT_USER_APP_PROC' not in s:
    if allow_anchor not in s:
        raise SystemExit('core_hook: allow uid anchor missing')
    # Insert after the allow-uid block by locating its return and close.
    pos = s.find(allow_anchor)
    end = s.find('\n\t}\n', pos)
    if end < 0:
        raise SystemExit('core_hook: allow uid block end missing')
    end += len('\n\t}\n')
    state = '''
#ifdef CONFIG_KSU_SUSFS
\ttask_lock(current);
\tcurrent->susfs_task_state |= TASK_STRUCT_NON_ROOT_USER_APP_PROC;
\ttask_unlock(current);
#endif
'''
    s = s[:end] + state + s[end:]

# The partially applied patch may already have the label. Otherwise add it
# immediately before KSU's should-umount decision.
if 'out_ksu_try_umount:' not in s:
    anchor = '\tif (!ksu_uid_should_umount(new_uid.val)) {\n'
    if anchor not in s:
        raise SystemExit('core_hook: uid_should_umount anchor missing')
    s = s.replace(anchor, '#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\nout_ksu_try_umount:\n#endif\n' + anchor, 1)

# Reuse the zygote result when SUSFS mount handling is enabled.
old = '\tif (!ksu_is_zygote(old->security)) {\n'
if old not in s:
    old = '\tif (!is_zygote(old->security)) {\n'
if old in s:
    new = '''#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tif (!is_zygote_child) {
#else
\tif (!ksu_is_zygote(old->security)) {
#endif
'''
    s = s.replace(old, new, 1)

# Put SUSFS try-umount ahead of KSU's normal list while retaining KSU Next's
# extra odm/system_ext/hosts/dex2oat handling when SUSFS is disabled.
start = '\t// fixme: use `collect_mounts` and `iterate_mount` to iterate all mountpoint and\n'
if '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n\tsusfs_try_umount_all(new_uid.val);' not in s:
    if start not in s:
        raise SystemExit('core_hook: umount list anchor missing')
    s = s.replace(start,
        '#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT\n'
        '\tsusfs_try_umount_all(new_uid.val);\n'
        '#else\n' + start, 1)
    end = '\tksu_try_umount("/system/etc/hosts", false, MNT_DETACH);\n\n\t// try umount lsposed dex2oat bins\n'
    if end not in s:
        raise SystemExit('core_hook: hosts umount anchor missing')
    s = s.replace(end,
        '\tksu_try_umount("/system/etc/hosts", false, MNT_DETACH);\n'
        '#endif\n\n\t// try umount lsposed dex2oat bins\n', 1)

for token in (
    'bool susfs_is_allow_su(void)',
    'susfs_on_post_fs_data',
    'extern int ksu_handle_sepolicy(',
    'susfs_is_sid_equal(old->security, susfs_zygote_sid)',
    'out_ksu_try_umount:',
    'susfs_try_umount_all(new_uid.val);',
):
    if token not in s:
        raise SystemExit(f'core_hook compatibility token missing: {token}')
p.write_text(s)

# SELinux rules: repair all v1.5.4 rejects on KSU Next v1.1.1.
p = root / 'selinux/rules.c'
s = p.read_text()
s = s.replace('void apply_kernelsu_rules()', 'void ksu_apply_kernelsu_rules()', 1)
s = s.replace('int handle_sepolicy(', 'int ksu_handle_sepolicy(', 1)
s = re.sub(r'(?<![A-Za-z0-9_])getenforce\(\)', 'ksu_getenforce()', s)
if 'susfs_set_zygote_sid();' not in s:
    anchor = '\trcu_read_unlock();\n'
    block = '''#ifdef CONFIG_KSU_SUSFS
\tksu_allow(db, "zygote", "labeledfs", "filesystem", "unmount");
\tsusfs_set_init_sid();
\tsusfs_set_ksu_sid();
\tsusfs_set_zygote_sid();
#endif

'''
    if anchor not in s:
        raise SystemExit('selinux rules: rcu_read_unlock anchor missing')
    s = s.replace(anchor, block + anchor, 1)
p.write_text(s)

# KSU Next v1.1.1 is exactly driver 12851. Pin it after the SUSFS patch so
# copied/symlinked source cannot fall back to the no-.git version.
p = root / 'Makefile'
s = p.read_text()
start = s.find('# .git is a text file')
end = s.find('ifeq ($(shell grep -q " current_sid(void)"', start)
if start >= 0 and end > start:
    forced = ('KSU_VERSION := 12851\n'
              '$(info -- KernelSU-Next version: $(KSU_VERSION))\n'
              'ccflags-y += -DKSU_VERSION=$(KSU_VERSION)\n\n')
    s = s[:start] + forced + s[end:]
elif 'KSU_VERSION := 12851' not in s:
    raise SystemExit('KSU Makefile version block not found')
p.write_text(s)

# Normalize trailing patch artifacts.
for rel in ('Kconfig', 'apk_sign.c', 'apk_sign.h', 'core_hook.c',
            'selinux/rules.c', 'selinux/selinux.c', 'sucompat.c',
            'throne_tracker.c'):
    p = root / rel
    if not p.exists():
        continue
    lines = [line.rstrip() for line in p.read_text().splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    p.write_text('\n'.join(lines) + '\n')

# Strong checks.
checks = {
    'Makefile': ['KSU_VERSION := 12851'],
    'apk_sign.c': ['bool ksu_is_manager_apk(char *path)'],
    'core_hook.c': ['susfs_on_post_fs_data', 'susfs_try_umount_all(new_uid.val);'],
    'selinux/rules.c': ['void ksu_apply_kernelsu_rules()', 'susfs_set_zygote_sid();'],
}
for rel, tokens in checks.items():
    text = (root / rel).read_text()
    for token in tokens:
        if token not in text:
            raise SystemExit(f'{rel}: missing {token}')

print('KSU Next v1.1.1 + SUSFS v1.5.4 compatibility repaired')
