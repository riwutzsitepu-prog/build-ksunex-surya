#!/usr/bin/env python3
from pathlib import Path
import re
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

def load(rel):
    p = root / rel
    if not p.exists():
        raise SystemExit(f"[ERR] file tidak ada: {rel}")
    return p, p.read_text(errors="surrogateescape")

def save(p, s):
    p.write_text(s, errors="surrogateescape")

def ensure_include(rel):
    p, s = load(rel)
    inc = "#include <linux/kernelsu.h>"
    if inc in s:
        return
    marker = "#include <linux/syscalls.h>"
    if marker in s:
        s = s.replace(marker, marker + "\n" + inc, 1)
    else:
        ms = list(re.finditer(r"^#include <linux/[^>]+>\s*$", s, re.M))
        if not ms:
            raise SystemExit(f"[ERR] include marker tidak ditemukan di {rel}")
        pos = ms[-1].end()
        s = s[:pos] + "\n" + inc + s[pos:]
    save(p, s)

def insert_after_match(rel, patterns, code, unique):
    p, s = load(rel)
    if unique in s:
        return
    for pat in patterns:
        m = re.search(pat, s, re.M | re.S)
        if m:
            s = s[:m.end()] + "\n" + code + s[m.end():]
            save(p, s)
            return
    raise SystemExit(f"[ERR] target hook tidak ditemukan di {rel}")

h = root / "include/linux/kernelsu.h"
if not h.exists():
    h.write_text(r"""#ifndef _LINUX_KERNELSU_H
#define _LINUX_KERNELSU_H
#include <linux/fs.h>
#include <linux/types.h>
struct filename;
#ifdef CONFIG_KSU
int ksu_handle_execveat(int *fd, struct filename **filename_ptr, void *argv, void *envp, int *flags);
int ksu_handle_faccessat(int *dfd, const char __user **filename_user, int *mode, int *flags);
int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);
int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr, size_t *count_ptr, loff_t **pos);
#else
static inline int ksu_handle_execveat(int *fd, struct filename **filename_ptr, void *argv, void *envp, int *flags){return 0;}
static inline int ksu_handle_faccessat(int *dfd, const char __user **filename_user, int *mode, int *flags){return 0;}
static inline int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags){return 0;}
static inline int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr, size_t *count_ptr, loff_t **pos){return 0;}
#endif
#endif
""")

ensure_include("fs/exec.c")
insert_after_match(
    "fs/exec.c",
    [
        r"(?:static\s+)?int\s+do_execveat_common\s*\([^\)]*\(?:[^\)]*\)[^{]*\{",
        r"(?:static\s+)?int\s+do_execveat_common\s*\([^\)]*\)[^{]*\{",
    ],
    "\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);",
    "ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);",
)

ensure_include("fs/open.c")
insert_after_match(
    "fs/open.c",
    [
        r"(SYSCALL_DEFINE3\(faccessat,\s*int,\s*dfd,\s*const char __user \*,\s*filename,\s*int,\s*mode\)\s*\{)",
        r"(long\s+do_faccessat\s*\(\s*int\s+dfd,\s*const char __user \*filename,\s*int\s+mode\s*\)\s*\{)",
    ],
    "\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);",
    "ksu_handle_faccessat(&dfd, &filename, &mode, NULL);",
)

ensure_include("fs/read_write.c")
insert_after_match(
    "fs/read_write.c",
    [r"(ssize_t\s+vfs_read\s*\(\s*struct file \*file,\s*char __user \*buf,\s*size_t count,\s*loff_t \*pos\s*\)\s*\{)"],
    "\tksu_handle_vfs_read(&file, &buf, &count, &pos);",
    "ksu_handle_vfs_read(&file, &buf, &count, &pos);",
)

ensure_include("fs/stat.c")
p, s = load("fs/stat.c")
if "ksu_handle_stat(&dfd, &filename" not in s:
    candidates = [
        (r"(int\s+vfs_fstatat\s*\(\s*int\s+dfd,\s*const char __user \*filename,\s*struct kstat \*stat,\s*int\s+flag\s*\)\s*\{)", "flag"),
        (r"(int\s+vfs_statx\s*\(\s*int\s+dfd,\s*const char __user \*filename,\s*int\s+flags[^\)]*\)\s*\{)", "flags"),
    ]
    for pat, flag in candidates:
        m = re.search(pat, s, re.M | re.S)
        if m:
            s = s[:m.end()] + f"\n\tksu_handle_stat(&dfd, &filename, &{flag});" + s[m.end():]
            save(p, s)
            break
    else:
        raise SystemExit("[ERR] vfs_fstatat/vfs_statx tidak ditemukan")

print("[OK] manual hooks KSUNext v1.1.1: execveat/faccessat/vfs_read/stat")
