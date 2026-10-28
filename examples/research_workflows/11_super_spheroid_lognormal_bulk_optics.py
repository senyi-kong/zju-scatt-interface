"""Calculate one-shape lognormal dust bulk optics at 1.6 um.

Role:
    Production example

Inputs:
    ensemble_bulk_config.py and PARAMETERS; Dg=1.4 um is diameter, sigma_g=1.8, N=10 cm^-3.

Outputs:
    Application NC at N=10, scalar/phase/PSD CSVs, summary JSON and normalized N=1 L2.

Run:
    python 11_super_spheroid_lognormal_bulk_optics.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Lognormal dust bulk optics: Dg=1.4 um, sigma_g=1.8, N=10 cm^-3.

    Dg is a volume-equivalent diameter, so the PSD geometric mean radius is 0.7 um.
    The application output retains N=10; the explicitly requested L2 product uses N=1.
"""
# ruff: noqa: E402
import argparse
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()

from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.psd.analytical import lognormal_psd
from zju_scatt_interface.access.retrieval import retrieve_sources
from zju_scatt_interface.io.l2 import write_l2_lognormal

# INPUT: settings shared with the two shape-ensemble examples.
from ensemble_bulk_config import FAMILY, WAVELENGTH_UM, DG_UM, SIGMA_G, N_CM3, COMMON, PSD_SETTINGS, CALCULATION_OPTIONS
PARAMETERS = {**COMMON, "ssph_n": 2.0, "ssph_asp": 1.6}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Select from a saved catalog")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--no-track", action="store_true", help="Use cached sources without online usage tracking")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.output_dir or Path(__file__).resolve().parent / "downloads/super_spheroid_lognormal_bulk"
    manifest = root / "selection_manifest.jsonl"
    downloaded = retrieve_sources(manifest=args.manifest, particle_types=FAMILY,
        shapes={"ssph_n": PARAMETERS["ssph_n"], "ssph_asp": PARAMETERS["ssph_asp"]},
        target_wavelengths=[WAVELENGTH_UM],
        refractive_index_parameters={FAMILY: {"mr": PARAMETERS["mr"], "mi": PARAMETERS["mi"]}},
        apply_interpolation=False, download=not args.list_only, manifest_output=manifest,
        output_dir=root / "sources", quiet=False, no_track=args.no_track)
    downloaded.raise_for_status(download=not args.list_only, require_matches=True)
    downloaded.write_report(root / "retrieval_report.json")
    if args.list_only:
        print(f"Selected {len(downloaded.objects)} sources: {manifest}")
        return
    sources = [item.target for item in downloaded.download_results]
    psd = lognormal_psd(**PSD_SETTINGS)
    calculation = compute_population(FAMILY, sources, psd,
        wavelength=WAVELENGTH_UM, parameters=PARAMETERS, **CALCULATION_OPTIONS)
    outputs = calculation.save(root, component_name="super_spheroid_lognormal",
        source_manifest=str(manifest), size_distribution=psd,
        netcdf_path="application_outputs/bulk_optics_10_cm3.nc",
        title="Super-spheroid lognormal population: Dg=1.4 um, sigma_g=1.8, N=10 cm-3")
    # Optional standardized, number-normalized L2 export is explicitly requested.
    outputs["l2"] = str(write_l2_lognormal(root, calculation.bulk,
        wavelength_um=WAVELENGTH_UM, parameters=PARAMETERS, rg_um=DG_UM/2,
        sigma_g=SIGMA_G, source_path=sources[0], psd_metadata=psd.metadata,
        documentation_sources=[__file__]))
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()
