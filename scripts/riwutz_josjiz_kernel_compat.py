#!/usr/bin/env python3
from pathlib import Path
import sys

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('kernel')

# fs/dcache.c: only the __d_lookup_rcu SUS_PATH hunk differs on Watermelon.
p = base / 'fs/dcache.c'
s = p.read_text()
needle = '''\t\tif (dentry_cmp(dentry, str, hashlen_len(hashlen)) != 0)\n\t\t\tcontinue;\n\t\t*seqp = seq;\n'''
insert = '''\t\tif (dentry_cmp(dentry, str, hashlen_len(hashlen)) != 0)\n\t\t\tcontinue;\n#ifdef CONFIG_KSU_SUSFS_SUS_PATH\n\t\tif (dentry->d_inode && unlikely(dentry->d_inode->i_state & INODE_STATE_SUS_PATH) && likely(current->susfs_task_state & TASK_STRUCT_NON_ROOT_USER_APP_PROC)) {\n\t\t\tcontinue;\n\t\t}\n#endif\n\t\t*seqp = seq;\n'''
if 'dentry->d_inode->i_state & INODE_STATE_SUS_PATH' not in s.split('struct dentry *d_lookup', 1)[0]:
    if needle not in s:
        raise SystemExit('dcache: __d_lookup_rcu anchor missing')
    s = s.replace(needle, insert, 1)
p.write_text(s)

# fs/proc/cmdline.c: Watermelon has a simple /proc/cmdline implementation.
p = base / 'fs/proc/cmdline.c'
s = p.read_text()
if 'extern int susfs_spoof_cmdline_or_bootconfig' not in s:
    anchor = '#include <linux/seq_file.h>\n\n'
    block = '''#include <linux/seq_file.h>\n\n#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\nextern int susfs_spoof_cmdline_or_bootconfig(struct seq_file *m);\n#endif\n\n'''
    if anchor not in s:
        raise SystemExit('cmdline: include anchor missing')
    s = s.replace(anchor, block, 1)
if 'susfs_spoof_cmdline_or_bootconfig(m)' not in s:
    anchor = 'static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n'
    block = '''static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n\tif (!susfs_spoof_cmdline_or_bootconfig(m)) {\n\t\tseq_putc(m, '\\n');\n\t\treturn 0;\n\t}\n#endif\n'''
    if anchor not in s:
        raise SystemExit('cmdline: show anchor missing')
    s = s.replace(anchor, block, 1)
p.write_text(s)

# fs/proc/task_mmu.c: helper/body hunks apply; Watermelon only needs the include.
p = base / 'fs/proc/task_mmu.c'
s = p.read_text()
if '#include <linux/susfs_def.h>' not in s:
    anchor = '#include <linux/ctype.h>\n'
    block = '''#include <linux/ctype.h>\n#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n#include <linux/susfs_def.h>\n#endif\n'''
    if anchor not in s:
        raise SystemExit('task_mmu: include anchor missing')
    s = s.replace(anchor, block, 1)
p.write_text(s)

# kernel/sys.c: preserve Watermelon bpfloader/netd fake-uname logic and run SUSFS first.
p = base / 'kernel/sys.c'
s = p.read_text()
if 'extern void susfs_spoof_uname' not in s:
    anchor = 'SYSCALL_DEFINE1(newuname, struct new_utsname __user *, name)\n'
    block = '''#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nextern void susfs_spoof_uname(struct new_utsname* tmp);\n#endif\nSYSCALL_DEFINE1(newuname, struct new_utsname __user *, name)\n'''
    if anchor not in s:
        raise SystemExit('sys.c: newuname anchor missing')
    s = s.replace(anchor, block, 1)
if 'susfs_spoof_uname(&tmp);' not in s:
    anchor = '\tmemcpy(&tmp, utsname(), sizeof(tmp));\n'
    block = '''\tmemcpy(&tmp, utsname(), sizeof(tmp));\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\n\tsusfs_spoof_uname(&tmp);\n#endif\n'''
    if anchor not in s:
        raise SystemExit('sys.c: memcpy anchor missing')
    s = s.replace(anchor, block, 1)
p.write_text(s)

# kernel/sched/fair.c: Android 10 disables UCLAMP_TASK, so its fallback calls
# boosted_task_util() before Watermelon defines it later in the same file.
# Add only a forward declaration; this does not change scheduler behaviour.
p = base / 'kernel/sched/fair.c'
s = p.read_text()
prototype = 'static inline unsigned long boosted_task_util(struct task_struct *task);\n\n'
anchor = '#ifdef CONFIG_UCLAMP_TASK\nstatic inline unsigned long uclamp_task_util(struct task_struct *p)\n'
pos = s.find(anchor)
if pos < 0:
    raise SystemExit('fair.c: uclamp_task_util anchor missing')
if prototype not in s[:pos + len(anchor)]:
    s = s[:pos] + prototype + s[pos:]
p.write_text(s)

# Strong semantic checks for all adaptations.
checks = {
    base / 'fs/dcache.c': [
        '#include <linux/susfs_def.h>',
        'TASK_STRUCT_NON_ROOT_USER_APP_PROC',
    ],
    base / 'fs/proc/cmdline.c': [
        'extern int susfs_spoof_cmdline_or_bootconfig',
        'susfs_spoof_cmdline_or_bootconfig(m)',
    ],
    base / 'fs/proc/task_mmu.c': [
        '#include <linux/susfs_def.h>',
        'susfs_sus_ino_for_show_map_vma',
        'INODE_STATE_SUS_KSTAT',
    ],
    base / 'kernel/sys.c': [
        'extern void susfs_spoof_uname',
        'susfs_spoof_uname(&tmp);',
        'bpfloader',
        'netd',
    ],
    base / 'kernel/sched/fair.c': [
        'static inline unsigned long boosted_task_util(struct task_struct *task);',
        'static inline unsigned long uclamp_task_util(struct task_struct *p)',
    ],
}
for fn, tokens in checks.items():
    text = fn.read_text()
    for token in tokens:
        if token not in text:
            raise SystemExit(f'{fn}: validation token missing: {token}')
