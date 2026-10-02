#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "kernel")
p = root / "drivers/usb/phy/phy-msm-qusb-v2.c"
s = p.read_text()

# Poco X3 Android 10 reference DTB uses the older QUSB2-v2 register layout:
#   10 offsets: ... DEBUG_CTRL2, STAT5
# Watermelon 4.14.355 added DEBUG_CTRL3/DEBUG_CTRL4 before STAT5 and requires
# 12 offsets, which makes the old DTB fail probe with -EINVAL. Keep the newer
# 4.14.355 driver but teach it to translate the legacy 10-entry layout.

struct_old = "\tbool\t\t\toverride_bias_ctrl2;\n};\n"
struct_new = "\tbool\t\t\toverride_bias_ctrl2;\n\tbool\t\t\tlegacy_reg_layout;\n};\n"
if struct_new not in s:
    if struct_old not in s:
        raise SystemExit("QUSB struct anchor missing")
    s = s.replace(struct_old, struct_new, 1)

old = '''\tsize = 0;\n\tof_get_property(dev->of_node, "qcom,qusb-phy-reg-offset", &size);\n\tif (size) {\n\t\tqphy->phy_reg = devm_kzalloc(dev, size, GFP_KERNEL);\n\t\tif (qphy->phy_reg) {\n\t\t\tqphy->qusb_phy_reg_offset_cnt =\n\t\t\t\tsize / sizeof(*qphy->phy_reg);\n\t\t\tif (qphy->qusb_phy_reg_offset_cnt != USB2_PHY_REG_MAX) {\n\t\t\t\tdev_err(dev, "invalid reg offset count\\n");\n\t\t\t\treturn -EINVAL;\n\t\t\t}\n\n\t\t\tof_property_read_u32_array(dev->of_node,\n\t\t\t\t\t"qcom,qusb-phy-reg-offset",\n\t\t\t\t\tqphy->phy_reg,\n\t\t\t\t\tqphy->qusb_phy_reg_offset_cnt);\n\t\t} else {\n\t\t\tdev_err(dev, "err mem alloc for qusb_phy_reg_offset\\n");\n\t\t\treturn -ENOMEM;\n\t\t}\n\t} else {\n\t\tdev_err(dev, "err provide qcom,qmp-phy-reg-offset\\n");\n\t\treturn -EINVAL;\n\t}\n'''
new = '''\tsize = 0;\n\tof_get_property(dev->of_node, "qcom,qusb-phy-reg-offset", &size);\n\tif (size) {\n\t\tint reg_count = size / sizeof(*qphy->phy_reg);\n\t\tunsigned int *legacy_reg;\n\n\t\tqphy->phy_reg = devm_kcalloc(dev, USB2_PHY_REG_MAX,\n\t\t\t\t\t sizeof(*qphy->phy_reg), GFP_KERNEL);\n\t\tif (!qphy->phy_reg) {\n\t\t\tdev_err(dev, "err mem alloc for qusb_phy_reg_offset\\n");\n\t\t\treturn -ENOMEM;\n\t\t}\n\n\t\tif (reg_count == USB2_PHY_REG_MAX) {\n\t\t\tqphy->qusb_phy_reg_offset_cnt = reg_count;\n\t\t\tof_property_read_u32_array(dev->of_node,\n\t\t\t\t\t"qcom,qusb-phy-reg-offset",\n\t\t\t\t\tqphy->phy_reg, reg_count);\n\t\t} else if (reg_count == USB2_PHY_REG_MAX - 2) {\n\t\t\t/* Legacy layout has no DEBUG_CTRL3/DEBUG_CTRL4 and its\n\t\t\t * final entry is STAT5. Translate it into the new array.\n\t\t\t */\n\t\t\tlegacy_reg = devm_kcalloc(dev, reg_count,\n\t\t\t\t\t\t sizeof(*legacy_reg), GFP_KERNEL);\n\t\t\tif (!legacy_reg)\n\t\t\t\treturn -ENOMEM;\n\t\t\tof_property_read_u32_array(dev->of_node,\n\t\t\t\t\t"qcom,qusb-phy-reg-offset",\n\t\t\t\t\tlegacy_reg, reg_count);\n\t\t\tmemcpy(qphy->phy_reg, legacy_reg,\n\t\t\t\tDEBUG_CTRL3 * sizeof(*legacy_reg));\n\t\t\tqphy->phy_reg[STAT5] = legacy_reg[reg_count - 1];\n\t\t\tqphy->qusb_phy_reg_offset_cnt = USB2_PHY_REG_MAX;\n\t\t\tqphy->legacy_reg_layout = true;\n\t\t\tdev_info(dev,\n\t\t\t\t"RIWUTZ_BOOTFIX8_QUSB_LEGACY10: accepted %d-register DT layout\\n",\n\t\t\t\treg_count);\n\t\t} else {\n\t\t\tdev_err(dev, "invalid reg offset count %d (expected %d or %d)\\n",\n\t\t\t\treg_count, USB2_PHY_REG_MAX, USB2_PHY_REG_MAX - 2);\n\t\t\treturn -EINVAL;\n\t\t}\n\t} else {\n\t\tdev_err(dev, "err provide qcom,qmp-phy-reg-offset\\n");\n\t\treturn -EINVAL;\n\t}\n'''
if new not in s:
    if old not in s:
        raise SystemExit("QUSB reg-offset probe block anchor missing")
    s = s.replace(old, new, 1)

assign_old = "\tqphy->phy.drive_dp_pulse\t= msm_qusb_phy_drive_dp_pulse;\n"
assign_new = "\tif (!qphy->legacy_reg_layout)\n\t\tqphy->phy.drive_dp_pulse = msm_qusb_phy_drive_dp_pulse;\n"
if assign_new not in s:
    if assign_old not in s:
        raise SystemExit("QUSB drive_dp_pulse assignment anchor missing")
    s = s.replace(assign_old, assign_new, 1)

p.write_text(s)

# Hard checks: never build a partial compatibility patch.
out = p.read_text()
assert "RIWUTZ_BOOTFIX8_QUSB_LEGACY10" in out
assert "reg_count == USB2_PHY_REG_MAX - 2" in out
assert "qphy->phy_reg[STAT5] = legacy_reg[reg_count - 1]" in out
assert "if (!qphy->legacy_reg_layout)" in out
print("BOOTFIX8 QUSB2 legacy 10-offset compatibility: VERIFIED")
