"""Rename RTTOV14 species and schemes to configured two-letter names.

Role:
    Production example

Inputs:
    23_rttov14_two_letter_config.py and existing tables; --recompute optionally rebuilds.

Outputs:
    Renamed NC products, including BC/DU/SS, and validation reports.

Run:
    python 23_default_scheme_rttov14_two_letter.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import argparse
import json
from pathlib import Path
import runpy
import shutil
import sys

from local_environment import verify_local_import
verify_local_import()
from zju_scatt_interface.io.applications.rttov.names import rename_rttov14_species


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=Path(__file__).with_name("23_rttov14_two_letter_config.py"))
    parser.add_argument("--recompute",action="store_true",help="Regenerate the default scheme before applying names")
    args=parser.parse_args()
    config=runpy.run_path(str(args.config))
    source,output=Path(config["source_dir"]),Path(config["output_dir"])
    paths=[Path(f"rttov_{root}_zju_lookup.nc") for root in ("aertable","hydrotable")]
    paths += [Path("native_slice")/f"rttov_{root}_zju_selected.nc" for root in ("aertable","hydrotable")]
    if args.recompute or not all((source/p).is_file() for p in paths):
        # Build the DEFAULT scheme from configuration 21, not custom shapes 22.
        default=Path(__file__).with_name("21_rttov14_lookup_config.py")
        base=runpy.run_path(str(default))
        if Path(base["output_dir"]).resolve()!=source.resolve():
            raise ValueError("Missing source tables: generate the configured source_dir first")
        previous=sys.argv
        try:
            sys.argv=["21_default_bulk_rttov14_lookup.py","--config",str(default)]
            runpy.run_path(str(default.with_name("21_default_bulk_rttov14_lookup.py")))["main"]()
        finally:
            sys.argv=previous
    source_manifest=json.loads((source/"rttov14_lookup_manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("shape_overrides"):
        raise ValueError("Expected the default scheme, but the source manifest contains shape overrides")
    names=config["output_names"]
    actual=set(source_manifest["populations"])
    if set(names)!=actual or len(set(names.values()))!=len(names) or any(
            not isinstance(n,str) or len(n)!=2 or not n.isascii() or not n.isalpha() for n in names.values()):
        raise ValueError("Configure one unique two-letter ASCII name for every species")
    products={}
    for relative in paths:
        products[str(relative)]=rename_rttov14_species(source/relative,output/relative,names)
        print(f"RTTOV14: {output/relative}")
    shutil.copy2(source/"channel_wavelengths.csv",output/"channel_wavelengths.csv")
    # Keep the full default-scheme provenance, keyed by the actual output names.
    source_manifest["populations"]={names[k]:{**v,"original_species_name":k}
                                    for k,v in source_manifest["populations"].items()}
    source_manifest["output_names"]=names
    source_manifest["naming_source_dir"]=str(source)
    source_manifest["named_outputs"]=products
    source_manifest["outputs"]={root:str(output/f"rttov_{root}_zju_lookup.nc") for root in ("aertable","hydrotable")}
    source_manifest["validation"]={root:products[f"rttov_{root}_zju_lookup.nc"]["validation"] for root in ("aertable","hydrotable")}
    (output/"rttov14_lookup_manifest.json").write_text(json.dumps(source_manifest,indent=2),encoding="utf-8")
    selection=json.loads((source/"native_slice/selection.json").read_text(encoding="utf-8"))
    selection["selection"]["aerosol_effective_radii_um"]={names[k]:v for k,v in
        selection["selection"]["aerosol_effective_radii_um"].items()}
    selection["validation"]={root:products[str(Path("native_slice")/f"rttov_{root}_zju_selected.nc")]["validation"]
                             for root in ("aertable","hydrotable")}
    (output/"native_slice/selection.json").write_text(json.dumps(selection,indent=2),encoding="utf-8")
    print("Only output names changed; default optical values and lookup axes are preserved exactly.")


if __name__=="__main__":
    main()
