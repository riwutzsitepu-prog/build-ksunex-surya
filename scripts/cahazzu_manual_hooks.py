import re
from pathlib import Path

def before(path, pattern, block, marker, desc):
    p = Path(path)
    s = p.read_text()
    if marker in s:
        return
    m = re.search(pattern, s, flags=re.MULTILINE | re.DOTALL)
    if not m:
        raise SystemExit(f"{desc}: declaration anchor not found in {path}")
    s = s[:m.start()] + block + "\n\n" + s[m.start():]
    p.write_text(s)

def after_open(path, pattern, block, marker, desc):
    p = Path(path)
    s = p.read_text()
    if marker in s:
        return
    m = re.search(pattern, s, flags=re.MULTILINE | re.DOTALL)
    if not m:
        raise SystemExit(f"{desc}: function anchor not found in {path}")
    s = s[:m.end()] + "\n" + block + s[m.end():]
    p.write_text(s)

# security/security.c: manual security hooks, no KSU LSM registration.
before(
    "security/security.c",
    r"/\* Security operations \*/",
    """#ifdef CONFIG_KSU
extern int ksu_handle_prctl(int option, unsigned long arg2, unsigned long arg3,
                            unsigned long arg4, unsigned long arg5);
extern int ksu_handle_rename(struct dentry *old_dentry, struct dentry *new_dentry);
extern int ksu_handle_setuid(struct cred *new, const struct cred *old);
#endif""",
    "extern int ksu_handle_prctl",
    "security declarations",
)
after_open(
    "security/security.c",
    r"int security_inode_rename\(struct inode \*old_dir, struct dentry \*old_dentry,\s*"
    r"struct inode \*new_dir, struct dentry \*new_dentry,\s*"
    r"unsigned int flags\)\s*\{",
    """#ifdef CONFIG_KSU
    ksu_handle_rename(old_dentry, new_dentry);
#endif""",
    "ksu_handle_rename(old_dentry, new_dentry);",
    "security rename",
)
after_open(
    "security/security.c",
    r"int security_task_fix_setuid\(struct cred \*new, const struct cred \*old,\s*"
    r"int flags\)\s*\{",
    """#ifdef CONFIG_KSU
    ksu_handle_setuid(new, old);
#endif""",
    "ksu_handle_setuid(new, old);",
    "security setuid",
)
after_open(
    "security/security.c",
    r"int security_task_prctl\(int option, unsigned long arg2, unsigned long arg3,\s*"
    r"unsigned long arg4, unsigned long arg5\)\s*\{",
    """#ifdef CONFIG_KSU
    ksu_handle_prctl(option, arg2, arg3, arg4, arg5);
#endif""",
    "ksu_handle_prctl(option, arg2, arg3, arg4, arg5);",
    "security prctl",
)

# fs/exec.c
before(
    "fs/exec.c",
    r"static int do_execveat_common\(int fd, struct filename \*filename,",
    """#ifdef CONFIG_KSU
extern bool ksu_execveat_hook __read_mostly;
extern int ksu_handle_execveat_ksud(int *fd, struct filename **filename_ptr,
                                    struct user_arg_ptr *argv,
                                    struct user_arg_ptr *envp, int *flags);
extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,
                                       void *argv, void *envp, int *flags);
#endif""",
    "extern bool ksu_execveat_hook",
    "exec declarations",
)
after_open(
    "fs/exec.c",
    r"static int do_execveat_common\(int fd, struct filename \*filename,\s*"
    r"struct user_arg_ptr argv,\s*struct user_arg_ptr envp,\s*int flags\)\s*\{",
    """#ifdef CONFIG_KSU
    if (unlikely(ksu_execveat_hook))
        ksu_handle_execveat_ksud(&fd, &filename, &argv, &envp, &flags);
    else
        ksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);
#endif""",
    "ksu_handle_execveat_ksud(&fd",
    "exec hook",
)

# fs/open.c
before(
    "fs/open.c",
    r"SYSCALL_DEFINE3\(faccessat, int, dfd, const char __user \*, filename, int, mode\)",
    """#ifdef CONFIG_KSU
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
                                int *mode, int *flags);
#endif""",
    "extern int ksu_handle_faccessat",
    "faccessat declarations",
)
after_open(
    "fs/open.c",
    r"SYSCALL_DEFINE3\(faccessat, int, dfd, const char __user \*, filename, int, mode\)\s*\{",
    """#ifdef CONFIG_KSU
    ksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif""",
    "ksu_handle_faccessat(&dfd",
    "faccessat hook",
)

# fs/read_write.c
before(
    "fs/read_write.c",
    r"SYSCALL_DEFINE3\(read, unsigned int, fd, char __user \*, buf, size_t, count\)",
    """#ifdef CONFIG_KSU
extern bool ksu_vfs_read_hook __read_mostly;
extern int ksu_handle_sys_read(unsigned int fd, char __user **buf_ptr,
                               size_t *count_ptr);
#endif""",
    "extern bool ksu_vfs_read_hook",
    "read declarations",
)
after_open(
    "fs/read_write.c",
    r"SYSCALL_DEFINE3\(read, unsigned int, fd, char __user \*, buf, size_t, count\)\s*\{",
    """#ifdef CONFIG_KSU
    if (unlikely(ksu_vfs_read_hook))
        ksu_handle_sys_read(fd, &buf, &count);
#endif""",
    "ksu_handle_sys_read(fd, &buf, &count);",
    "read hook",
)

# fs/stat.c
before(
    "fs/stat.c",
    r"SYSCALL_DEFINE4\(newfstatat, int, dfd, const char __user \*, filename,",
    """#ifdef CONFIG_KSU
extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);
#endif""",
    "extern int ksu_handle_stat",
    "stat declarations",
)
after_open(
    "fs/stat.c",
    r"SYSCALL_DEFINE4\(newfstatat, int, dfd, const char __user \*, filename,\s*"
    r"struct stat __user \*, statbuf, int, flag\)\s*\{",
    """#ifdef CONFIG_KSU
    ksu_handle_stat(&dfd, &filename, &flag);
#endif""",
    "ksu_handle_stat(&dfd, &filename, &flag);",
    "stat hook",
)

# drivers/input/input.c
before(
    "drivers/input/input.c",
    r"static void input_handle_event\(struct input_dev \*dev,",
    """#ifdef CONFIG_KSU
extern bool ksu_input_hook __read_mostly;
extern int ksu_handle_input_handle_event(unsigned int *type,
                                         unsigned int *code, int *value);
#endif""",
    "extern bool ksu_input_hook",
    "input declarations",
)
after_open(
    "drivers/input/input.c",
    r"static void input_handle_event\(struct input_dev \*dev,\s*"
    r"unsigned int type, unsigned int code, int value\)\s*\{",
    """#ifdef CONFIG_KSU
    if (unlikely(ksu_input_hook))
        ksu_handle_input_handle_event(&type, &code, &value);
#endif""",
    "ksu_handle_input_handle_event(&type, &code, &value);",
    "input hook",
)

# drivers/tty/pty.c
before(
    "drivers/tty/pty.c",
    r"static struct tty_struct \*pts_unix98_lookup\(struct tty_driver \*driver,",
    """#ifdef CONFIG_KSU
extern int ksu_handle_devpts(struct inode *inode);
#endif""",
    "extern int ksu_handle_devpts",
    "devpts declarations",
)
after_open(
    "drivers/tty/pty.c",
    r"static struct tty_struct \*pts_unix98_lookup\(struct tty_driver \*driver,\s*"
    r"struct file \*file, int idx\)\s*\{",
    """#ifdef CONFIG_KSU
    ksu_handle_devpts(file->f_path.dentry->d_inode);
#endif""",
    "ksu_handle_devpts(file->f_path.dentry->d_inode);",
    "devpts hook",
)

print("manual hooks patched")
