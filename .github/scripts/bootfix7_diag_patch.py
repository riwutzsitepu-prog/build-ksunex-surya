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

# BOOTFIX6 compatibility fixes.
patch_once(
    "kernel/sched/fair.c",
    "return max(task_util(p), _task_util_est(p));\n}\n\n#ifdef CONFIG_UCLAMP_TASK\n",
    "return max(task_util(p), _task_util_est(p));\n}\n\nstatic inline unsigned long boosted_task_util(struct task_struct *task);\n\n#ifdef CONFIG_UCLAMP_TASK\n",
    "boosted_task_util declaration",
)

patch_once(
    "block/mq-deadline.c",
    "static struct request *__dd_dispatch_request(struct deadline_data *dd)\n{\n\tstruct deadline_data *dd = hctx->queue->elevator->elevator_data;\n",
    "static struct request *__dd_dispatch_request(struct deadline_data *dd)\n{\n",
    "mq-deadline duplicate dd",
)

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

# BOOTFIX7: if device CMA cannot satisfy a coherent allocation, fall back to
# SWIOTLB instead of returning NULL immediately.
patch_once(
    "arch/arm64/mm/dma-mapping.c",
    "\t\tpage = dma_alloc_from_contiguous(dev, size >> PAGE_SHIFT,\n"
    "\t\t\t\t\t\t get_order(size), flags);\n"
    "\t\tif (!page)\n"
    "\t\t\treturn NULL;\n\n"
    "\t\t*dma_handle = phys_to_dma(dev, page_to_phys(page));\n"
    "\t\taddr = page_address(page);\n"
    "\t\tmemset(addr, 0, size);\n"
    "\t} else {\n"
    "\t\taddr = swiotlb_alloc_coherent(dev, size, dma_handle, flags);\n"
    "\t}\n",
    "\t\tpage = dma_alloc_from_contiguous(dev, size >> PAGE_SHIFT,\n"
    "\t\t\t\t\t\t get_order(size), flags);\n"
    "\t\tif (page) {\n"
    "\t\t\t*dma_handle = phys_to_dma(dev, page_to_phys(page));\n"
    "\t\t\taddr = page_address(page);\n"
    "\t\t\tmemset(addr, 0, size);\n"
    "\t\t} else {\n"
    "\t\t\tpr_warn_ratelimited(\"riwutz: CMA coherent alloc failed for %s (%zu), fallback SWIOTLB\\n\",\n"
    "\t\t\t\tdev_name(dev), size);\n"
    "\t\t\taddr = swiotlb_alloc_coherent(dev, size, dma_handle, flags);\n"
    "\t\t}\n"
    "\t} else {\n"
    "\t\taddr = swiotlb_alloc_coherent(dev, size, dma_handle, flags);\n"
    "\t}\n",
    "CMA to SWIOTLB fallback",
)

# BOOTFIX7: slow repeated USB PHY deferred probing so early boot cannot spin in
# a hot reprobe loop while PHY providers are not ready.
patch_once(
    "drivers/usb/dwc3/dwc3-msm.c",
    "\tif (IS_ERR(mdwc->hs_phy)) {\n"
    "\t\tdev_err(&pdev->dev, \"unable to get hsphy device\\n\");\n"
    "\t\tret = PTR_ERR(mdwc->hs_phy);\n"
    "\t\tgoto put_dwc3;\n"
    "\t}\n",
    "\tif (IS_ERR(mdwc->hs_phy)) {\n"
    "\t\tret = PTR_ERR(mdwc->hs_phy);\n"
    "\t\tif (ret == -EPROBE_DEFER) {\n"
    "\t\t\tdev_info_ratelimited(&pdev->dev, \"hsphy not ready; delaying reprobe\\n\");\n"
    "\t\t\tmsleep(100);\n"
    "\t\t} else {\n"
    "\t\t\tdev_err(&pdev->dev, \"unable to get hsphy device: %d\\n\", ret);\n"
    "\t\t}\n"
    "\t\tgoto put_dwc3;\n"
    "\t}\n",
    "HS PHY deferred-probe delay",
)

patch_once(
    "drivers/usb/dwc3/dwc3-msm.c",
    "\tif (IS_ERR(mdwc->ss_phy)) {\n"
    "\t\tdev_err(&pdev->dev, \"unable to get ssphy device\\n\");\n"
    "\t\tret = PTR_ERR(mdwc->ss_phy);\n"
    "\t\tgoto put_dwc3;\n"
    "\t}\n",
    "\tif (IS_ERR(mdwc->ss_phy)) {\n"
    "\t\tret = PTR_ERR(mdwc->ss_phy);\n"
    "\t\tif (ret == -EPROBE_DEFER) {\n"
    "\t\t\tdev_info_ratelimited(&pdev->dev, \"ssphy not ready; delaying reprobe\\n\");\n"
    "\t\t\tmsleep(100);\n"
    "\t\t} else {\n"
    "\t\t\tdev_err(&pdev->dev, \"unable to get ssphy device: %d\\n\", ret);\n"
    "\t\t}\n"
    "\t\tgoto put_dwc3;\n"
    "\t}\n",
    "SS PHY deferred-probe delay",
)

# Diagnostic only: warm panic after 45s so ramoops survives and can be read in
# OrangeFox. This does not belong in the final kernel.
p = root / "init/main.c"
s = p.read_text()
marker = "RIWUTZ_BOOTFIX7_DIAG_TIMEOUT_45S"
if marker not in s:
    diag = '''\n\n/* RIWUTZ BOOTFIX7 diagnostic: force a warm panic after 45 seconds. */\nstatic int riwutz_diag_timeout_thread(void *unused)\n{\n\tpr_emerg("RIWUTZ_BOOTFIX7_DIAG: 45-second timeout armed\\n");\n\tssleep(45);\n\tpanic_timeout = 5;\n\tpanic("RIWUTZ_BOOTFIX7_DIAG_TIMEOUT_45S");\n\treturn 0;\n}\n\nstatic int __init riwutz_diag_timeout_init(void)\n{\n\tstruct task_struct *task;\n\ttask = kthread_run(riwutz_diag_timeout_thread, NULL, "riwutz_diag");\n\tif (IS_ERR(task))\n\t\treturn PTR_ERR(task);\n\treturn 0;\n}\ncore_initcall(riwutz_diag_timeout_init);\n'''
    p.write_text(s + diag)
print("45s ramoops diagnostic timeout: OK")

# Hard assertions so CI never silently builds a partial patch.
assert "fallback SWIOTLB" in (root / "arch/arm64/mm/dma-mapping.c").read_text()
assert "hsphy not ready; delaying reprobe" in (root / "drivers/usb/dwc3/dwc3-msm.c").read_text()
assert "ssphy not ready; delaying reprobe" in (root / "drivers/usb/dwc3/dwc3-msm.c").read_text()
assert marker in (root / "init/main.c").read_text()
print("BOOTFIX7-DIAG source patch set: VERIFIED")
