#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "kernel")
p = root / "drivers/scsi/ufs/ufshcd-crypto-qti.c"
s = p.read_text()

# A10 surya DT uses a separate qcom,ice node referenced by the
# "ufs-qcom-crypto" phandle. Newer Watermelon expects a named "ufs_ice"
# resource inside the UFS host. Keep the newer binding first, then fall back
# to the legacy phandle without changing the 4.14.355 crypto implementation.
anchor_inc = "#include <linux/platform_device.h>\n"
extra_inc = (
    "#include <linux/platform_device.h>\n"
    "#include <linux/of.h>\n"
    "#include <linux/of_address.h>\n"
    "#include <linux/io.h>\n"
    "#include <linux/ioport.h>\n"
)
if "#include <linux/of_address.h>" not in s:
    if anchor_inc not in s:
        raise SystemExit("UFS include anchor missing")
    s = s.replace(anchor_inc, extra_inc, 1)

old = '''\tmem_res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "ufs_ice");
\tmmio_base = devm_ioremap_resource(hba->dev, mem_res);
\tif (IS_ERR(mmio_base)) {
\t\tpr_err("%s: Unable to get ufs_crypto mmio base\\n", __func__);
\t\treturn PTR_ERR(mmio_base);
\t}
'''
new = '''\tmem_res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "ufs_ice");
\tif (mem_res) {
\t\tmmio_base = devm_ioremap_resource(hba->dev, mem_res);
\t\tif (IS_ERR(mmio_base)) {
\t\t\tpr_err("%s: Unable to get ufs_crypto mmio base\\n", __func__);
\t\t\treturn PTR_ERR(mmio_base);
\t\t}
\t} else {
\t\tstruct device_node *ice_np;
\t\tstruct resource ice_res;

\t\tice_np = of_parse_phandle(hba->dev->of_node,
\t\t\t\t\t    "ufs-qcom-crypto", 0);
\t\tif (!ice_np) {
\t\t\tpr_err("%s: no ufs_ice resource or legacy ufs-qcom-crypto phandle\\n",
\t\t\t       __func__);
\t\t\treturn -ENODEV;
\t\t}

\t\terr = of_address_to_resource(ice_np, 0, &ice_res);
\t\tof_node_put(ice_np);
\t\tif (err) {
\t\t\tpr_err("%s: legacy ICE address translation failed: %d\\n",
\t\t\t       __func__, err);
\t\t\treturn err;
\t\t}

\t\t/* The legacy ICE node is a separate platform device and may own
\t\t * the resource already, so map its physical range without claiming
\t\t * it a second time.
\t\t */
\t\tmmio_base = devm_ioremap(hba->dev, ice_res.start,
\t\t\t\t\t resource_size(&ice_res));
\t\tif (!mmio_base) {
\t\t\tpr_err("%s: failed to map legacy ICE registers\\n", __func__);
\t\t\treturn -ENOMEM;
\t\t}

\t\tdev_info(hba->dev,
\t\t\t "RIWUTZ_BOOTFIX9_UFS_A10_PHANDLE: using legacy ICE DT node\\n");
\t}
'''

marker = "RIWUTZ_BOOTFIX9_UFS_A10_PHANDLE"
if marker not in s:
    if old not in s:
        raise SystemExit("UFS crypto MMIO anchor missing")
    s = s.replace(old, new, 1)

p.write_text(s)

check = p.read_text()
assert marker in check
assert 'of_parse_phandle(hba->dev->of_node' in check
assert '"ufs-qcom-crypto", 0' in check
assert 'devm_ioremap(hba->dev, ice_res.start' in check
print("BOOTFIX9 UFS legacy ICE phandle bridge: VERIFIED")
