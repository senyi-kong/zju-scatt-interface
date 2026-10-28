"""Export existing bulk optics into user-defined NetCDF and HDF5 layouts.

Role:
    Production example

Inputs:
    24_custom_output_config.py: source, species/group/axis/variable/unit mappings.

Outputs:
    Configured NC/HDF5 products and custom_output_validation.json.

Run:
    python 24_export_custom_output.py; append --help for options.

Notes:
    Inspects or exports existing information; it does not run a new single-scattering solver.
"""
import argparse
import json
from pathlib import Path
import runpy

from local_environment import verify_local_import
verify_local_import()
from zju_scatt_interface.io.custom import export_bulk_optics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=Path(__file__).with_name("24_custom_output_config.py"))
    parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args()
    config=runpy.run_path(str(args.config))
    source=Path(config["bulk_source"])
    if not source.is_absolute():
        source=args.config.resolve().parent/source
    result=export_bulk_optics(source,args.config,overwrite=args.overwrite)
    for path in result["outputs"]:
        print(f"Custom optical table: {path}")
    report=Path(result["outputs"][0]).with_name("custom_output_validation.json")
    report.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(f"Validation: {report}")


if __name__=="__main__":
    main()
