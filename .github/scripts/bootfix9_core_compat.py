#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "kernel")


def patch_once(rel, old, new, label):
    p = root / rel
    s = p.read_text()
    if new in s:
        print(f"{label}: already applied")
        return
    if old not in s:
        raise SystemExit(f"{label}: anchor missing in {rel}")
    p.write_text(s.replace(old, new, 1))
    print(f"{label}: OK")


# Required compatibility fixes for this exact 4.14.355 tree + A10 config.
patch_once(
    "kernel/sched/fair.c",
    "return max(task_util(p), _task_util_est(p));\n}\n\n#ifdef CONFIG_UCLAMP_TASK\n",
    "return max(task_util(p), _task_util_est(p));\n}\n\nstatic inline unsigned long boosted_task_util(struct task_struct *task);\n\n#ifdef CONFIG_UCLAMP_TASK\n",
    "boosted_task_util declaration",
)

p = root / "block/mq-deadline.c"
s = p.read_text()
needle = "static struct request *__dd_dispatch_request(struct deadline_data *dd)\n{\n\tstruct deadline_data *dd = hctx->queue->elevator->elevator_data;\n"
repl = "static struct request *__dd_dispatch_request(struct deadline_data *dd)\n{\n"
if needle in s:
    s = s.replace(needle, repl, 1)
elif "struct deadline_data *dd = hctx->queue->elevator->elevator_data;" in s:
    s = s.replace("\tstruct deadline_data *dd = hctx->queue->elevator->elevator_data;\n", "", 1)
elif "static struct request *__dd_dispatch_request(struct deadline_data *dd)" not in s:
    raise SystemExit("mq-deadline anchor missing")
p.write_text(s)
print("mq-deadline duplicate dd: OK")

p = root / "lib/lz4/lz4_decompress.c"
s = p.read_text()
s = s.replace("EXPORT_SYMBOL(LZ4_armv8_decompress_safe);", "EXPORT_SYMBOL(LZ4_arm64_decompress_safe);", 1)
s = s.replace("EXPORT_SYMBOL(LZ4_armv8_decompress_safe_partial);", "EXPORT_SYMBOL(LZ4_arm64_decompress_safe_partial);", 1)
p.write_text(s)
print("LZ4 arm64 exports: OK")

p = root / "drivers/soc/qcom/msm_bus/msm_bus_dbg_rpmh.c"
s = p.read_text()
trace_inc = "#include <trace/events/trace_msm_bus.h>"
if "#define CREATE_TRACE_POINTS" not in s:
    if trace_inc not in s:
        raise SystemExit("msm bus trace anchor missing")
    s = s.replace(trace_inc, "#define CREATE_TRACE_POINTS\n" + trace_inc, 1)
p.write_text(s)
print("MSM bus tracepoints: OK")

assert "static inline unsigned long boosted_task_util(struct task_struct *task);" in (root / "kernel/sched/fair.c").read_text()
mq = (root / "block/mq-deadline.c").read_text()
assert "static struct request *__dd_dispatch_request(struct deadline_data *dd)\n{\n\tstruct deadline_data *dd = hctx->queue->elevator->elevator_data;" not in mq
assert "static struct request *__dd_dispatch_request(struct deadline_data *dd)" in mq
assert "EXPORT_SYMBOL(LZ4_arm64_decompress_safe);" in (root / "lib/lz4/lz4_decompress.c").read_text()
assert "#define CREATE_TRACE_POINTS" in (root / "drivers/soc/qcom/msm_bus/msm_bus_dbg_rpmh.c").read_text()
print("BOOTFIX9 core compatibility set: VERIFIED")
