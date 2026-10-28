"""Round-trip downloaded/supplied official tables and save a verification report.

Role:
    Reference-format utility

Inputs:
    Reference manifest and accessible official files.

Outputs:
    Round-trip artifacts and verification report; no RTM executables invoked.

Run:
    From the package root: python examples/verify_native_references.py --help

Notes:
    Reference artifacts validate serialization independently of the user's production optical
    data.

Original example details:
    Round-trip downloaded/supplied official tables and save a verification report.

    Run download_native_references.py first. No radiative-transfer executables are
    invoked: this verifies serialization against independent official artifacts.
"""

import argparse
import json
from pathlib import Path

import h5py
import numpy as np

from zju_scatt_interface.io.native import (
    native_template_from_reference,
    read_native_optical_arrays,
    write_native_optical_output,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--manifest", type=Path, default=root / "reference_data/rtm_formats/manifest.json"
    )
    parser.add_argument(
        "--output", type=Path, default=root / "native_model_output/reference_roundtrips"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in json.loads(args.manifest.read_text())["references"]:
        source = Path(entry["path"])
        if source.suffix.lower() not in {".xml", ".nc", ".h5"}:
            continue
        model = {".xml": "arts2", ".nc": "crtm-cloud-v3", ".h5": "rttov13"}[source.suffix.lower()]
        template = native_template_from_reference(source, model=model)
        arrays = read_native_optical_arrays(source, model=model)
        target = write_native_optical_output(
            args.output / source.name, arrays, template, overwrite=True
        )
        recovered = read_native_optical_arrays(target, model=model)
        assert set(arrays) == set(recovered)
        for name in arrays:
            np.testing.assert_array_equal(arrays[name], recovered[name], err_msg=name)
        if model == "rttov13":
            with h5py.File(source) as left, h5py.File(target) as right:

                def compare(name, obj):
                    assert set(obj.attrs) == set(right[name].attrs), name
                    for key in obj.attrs:
                        np.testing.assert_array_equal(
                            obj.attrs[key], right[name].attrs[key], err_msg=f"{name}:{key}"
                        )
                    if isinstance(obj, h5py.Dataset):
                        assert obj.dtype == right[name].dtype, name

                left.visititems(compare)
        result = {
            "model": model,
            "reference": str(source),
            "output": str(target),
            "variables_equal": len(arrays),
            "passed": True,
        }
        if model == "crtm-cloud-v3":
            template["format"] = "crtm-binary"
            binary = write_native_optical_output(
                target.with_suffix(".bin"), arrays, template, overwrite=True
            )
            result["official_binary_byte_identical"] = (
                binary.read_bytes() == source.with_suffix(".bin").read_bytes()
            )
            assert result["official_binary_byte_identical"]
        results.append(result)
    path = args.output / "verification.json"
    path.write_text(
        json.dumps({"checks": results, "model_executables_run": False}, indent=2) + "\n"
    )
    print(path)


if __name__ == "__main__":
    main()
