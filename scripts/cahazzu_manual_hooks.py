from pathlib import Path

def once(path, old, new, desc):
    p = Path(path)
    s = p.read_text()
    if new in s:
        return
    if old not in s:
        raise SystemExit(f"{desc}: anchor not found in {path}")
    p.write_text(s.replace(old, new, 1))

p = Path("security/security.c")
s = p.read_text()
decl_anchor = "/* Security operations */"
decl = """#ifdef CONFIG_KSU
extern int ksu_handle_prctl(int option, unsigned long arg2, unsigned long arg3,
                            unsigned long arg4, unsigned long arg5);
extern int ksu_handle_rename(struct dentry *old_dentry, struct dentry *new_dentry);
extern int ksu_handle_setuid(struct cred *new, const struct cred *old);
#endif

/* Security operations */"""
if "extern int ksu_handle_prctl" not in s:
    if decl_anchor not in s:
        raise SystemExit("security declarations anchor not found")
    s = s.replace(decl_anchor, decl, 1)

import re

rename_pat = re.compile(
    r"(int security_inode_rename\(struct inode \*old_dir, struct dentry \*old_dentry,\s*"
    r"struct inode \*new_dir, struct dentry \*new_dentry,\s*"
    r"unsigned int flags\)\s*\{)"
)
if "ksu_handle_rename(old_dentry, new_dentry);" not in s:
    m = rename_pat.search(s)
    if not m:
        raise SystemExit("security rename anchor not found")
    hook = m.group(1) + """
#ifdef CONFIG_KSU
    ksu_handle_rename(old_dentry, new_dentry);
#endif"""
    s = s[:m.start()] + hook + s[m.end():]

setuid_pat = re.compile(
    r"(int security_task_fix_setuid\(struct cred \*new, const struct cred \*old,\s*"
    r"int flags\)\s*\{)"
)
if "ksu_handle_setuid(new, old);" not in s:
    m = setuid_pat.search(s)
    if not m:
        raise SystemExit("security setuid anchor not found")
    hook = m.group(1) + """
#ifdef CONFIG_KSU
    ksu_handle_setuid(new, old);
#endif"""
    s = s[:m.start()] + hook + s[m.end():]

old = """int security_task_prctl(int option, unsigned long arg2, unsigned long arg3,
                        unsigned long arg4, unsigned long arg5)
{"""
new = old + """
#ifdef CONFIG_KSU
    ksu_handle_prctl(option, arg2, arg3, arg4, arg5);
#endif"""
if "ksu_handle_prctl(option, arg2, arg3, arg4, arg5);" not in s:
    if old not in s:
        raise SystemExit("security prctl anchor not found")
    s = s.replace(old, new, 1)
p.write_text(s)

p = Path("fs/exec.c")
s = p.read_text()
anchor = """static int do_execveat_common(int fd, struct filename *filename,
                              struct user_arg_ptr argv,
                              struct user_arg_ptr envp,
                              int flags)
{"""
repl = """#ifdef CONFIG_KSU
extern bool ksu_execveat_hook __read_mostly;
extern int ksu_handle_execveat_ksud(int *fd, struct filename **filename_ptr,
                                    struct user_arg_ptr *argv,
                                    struct user_arg_ptr *envp, int *flags);
extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,
                                       void *argv, void *envp, int *flags);
#endif

static int do_execveat_common(int fd, struct filename *filename,
                              struct user_arg_ptr argv,
                              struct user_arg_ptr envp,
                              int flags)
{
#ifdef CONFIG_KSU
    if (unlikely(ksu_execveat_hook))
        ksu_handle_execveat_ksud(&fd, &filename, &argv, &envp, &flags);
    else
        ksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);
#endif"""
if "ksu_handle_execveat_ksud(&fd" not in s:
    if anchor not in s:
        raise SystemExit("exec hook anchor not found")
    s = s.replace(anchor, repl, 1)
    p.write_text(s)

once(
    "fs/open.c",
    """SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)
{""",
    """#ifdef CONFIG_KSU
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user,
                                int *mode, int *flags);
#endif

SYSCALL_DEFINE3(faccessat, int, dfd, const char __user *, filename, int, mode)
{
#ifdef CONFIG_KSU
    ksu_handle_faccessat(&dfd, &filename, &mode, NULL);
#endif""",
    "faccessat hook",
)

once(
    "fs/read_write.c",
    """SYSCALL_DEFINE3(read, unsigned int, fd, char __user *, buf, size_t, count)
{""",
    """#ifdef CONFIG_KSU
extern bool ksu_vfs_read_hook __read_mostly;
extern int ksu_handle_sys_read(unsigned int fd, char __user **buf_ptr,
                               size_t *count_ptr);
#endif

SYSCALL_DEFINE3(read, unsigned int, fd, char __user *, buf, size_t, count)
{
#ifdef CONFIG_KSU
    if (unlikely(ksu_vfs_read_hook))
        ksu_handle_sys_read(fd, &buf, &count);
#endif""",
    "read hook",
)

once(
    "fs/stat.c",
    """SYSCALL_DEFINE4(newfstatat, int, dfd, const char __user *, filename,
                struct stat __user *, statbuf, int, flag)
{""",
    """#ifdef CONFIG_KSU
extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);
#endif

SYSCALL_DEFINE4(newfstatat, int, dfd, const char __user *, filename,
                struct stat __user *, statbuf, int, flag)
{
#ifdef CONFIG_KSU
    ksu_handle_stat(&dfd, &filename, &flag);
#endif""",
    "stat hook",
)

once(
    "drivers/input/input.c",
    """static void input_handle_event(struct input_dev *dev,
                               unsigned int type, unsigned int code, int value)
{""",
    """#ifdef CONFIG_KSU
extern bool ksu_input_hook __read_mostly;
extern int ksu_handle_input_handle_event(unsigned int *type,
                                         unsigned int *code, int *value);
#endif

static void input_handle_event(struct input_dev *dev,
                               unsigned int type, unsigned int code, int value)
{
#ifdef CONFIG_KSU
    if (unlikely(ksu_input_hook))
        ksu_handle_input_handle_event(&type, &code, &value);
#endif""",
    "input hook",
)

once(
    "drivers/tty/pty.c",
    """static struct tty_struct *pts_unix98_lookup(struct tty_driver *driver,
                struct file *file, int idx)
{
    struct tty_struct *tty;

    mutex_lock(&devpts_mutex);""",
    """#ifdef CONFIG_KSU
extern int ksu_handle_devpts(struct inode *inode);
#endif

static struct tty_struct *pts_unix98_lookup(struct tty_driver *driver,
                struct file *file, int idx)
{
    struct tty_struct *tty;

#ifdef CONFIG_KSU
    ksu_handle_devpts(file->f_path.dentry->d_inode);
#endif

    mutex_lock(&devpts_mutex);""",
    "devpts hook",
)

print("manual hooks patched")
