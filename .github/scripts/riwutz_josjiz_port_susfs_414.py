#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
expected = {
    "fs/dcache.c.rej",
    "fs/proc/task_mmu.c.rej",
    "kernel/sys.c.rej",
}
rejects = {
    str(p.relative_to(root)) for p in root.rglob("*.rej")
    if "KernelSU-Next" not in p.parts
}
if rejects != expected:
    raise SystemExit(f"Unexpected SUSFS 4.14 rejects: {sorted(rejects)}; expected {sorted(expected)}")

# 1) Watermelon dcache has a slightly different __d_lookup_rcu body.
p = root / "fs/dcache.c"
s = p.read_text()
block = """#ifdef CONFIG_KSU_SUSFS_SUS_PATH
		if (dentry->d_inode && unlikely(dentry->d_inode->i_state & INODE_STATE_SUS_PATH) && likely(current->susfs_task_state & TASK_STRUCT_NON_ROOT_USER_APP_PROC)) {
			continue;
		}
#endif
"""
anchor = """		if (dentry_cmp(dentry, str, hashlen_len(hashlen)) != 0)
			continue;
		*seqp = seq;
"""
replacement = """		if (dentry_cmp(dentry, str, hashlen_len(hashlen)) != 0)
			continue;
""" + block + """		*seqp = seq;
"""
if block not in s:
    if anchor not in s:
        raise SystemExit("dcache Watermelon anchor not found")
    s = s.replace(anchor, replacement, 1)
p.write_text(s)

# 2) Watermelon task_mmu include ordering differs from vanilla 4.14.
p = root / "fs/proc/task_mmu.c"
s = p.read_text()
include = """#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
#include <linux/susfs_def.h>
#endif
"""
anchor = "#include <linux/shmem_fs.h>\n"
if include not in s:
    if anchor not in s:
        raise SystemExit("task_mmu shmem include anchor not found")
    s = s.replace(anchor, anchor + include, 1)
p.write_text(s)

# 3) Watermelon already carries its bpfloader/netd fake-uname logic.
# Keep that logic untouched and add SUSFS exactly after copying utsname, so
# Watermelon's special 4.19 override can still win for those system processes.
p = root / "kernel/sys.c"
s = p.read_text()
extern = """#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
extern void susfs_spoof_uname(struct new_utsname* tmp);
#endif

"""
func_anchor = "SYSCALL_DEFINE1(newuname, struct new_utsname __user *, name)\n"
if extern not in s:
    if func_anchor not in s:
        raise SystemExit("newuname function anchor not found")
    s = s.replace(func_anchor, extern + func_anchor, 1)
call = """#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
	susfs_spoof_uname(&tmp);
#endif
"""
copy_anchor = "\tmemcpy(&tmp, utsname(), sizeof(tmp));\n"
if call not in s:
    if copy_anchor not in s:
        raise SystemExit("newuname memcpy anchor not found")
    s = s.replace(copy_anchor, copy_anchor + call, 1)
p.write_text(s)

# Rejects are now resolved manually. Remove patch leftovers so later checks
# cannot mistake them for KernelSU patch rejects.
for rel in expected:
    q = root / rel
    if q.exists():
        q.unlink()
for q in root.rglob("*.orig"):
    if "KernelSU-Next" not in q.parts:
        q.unlink()

checks = {
    "fs/dcache.c": "INODE_STATE_SUS_PATH",
    "fs/proc/task_mmu.c": "CONFIG_KSU_SUSFS_SUS_KSTAT",
    "kernel/sys.c": "susfs_spoof_uname(&tmp);",
}
for rel, needle in checks.items():
    if needle not in (root / rel).read_text():
        raise SystemExit(f"manual SUSFS port verification failed: {rel}: {needle}")

print("SUSFS_4.14_WATERMELON_MANUAL_PORT=PASS")
