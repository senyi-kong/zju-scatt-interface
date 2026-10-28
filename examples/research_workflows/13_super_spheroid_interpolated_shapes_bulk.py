"""Interpolate three target dust shapes, integrate each PSD, then average bulk results.

Role:
    Production example

Inputs:
    ensemble_bulk_config.py EXAMPLES['13']: (n,asp)=(2.7,1.5),(2.8,1.9),(2.5,1.3).

Outputs:
    Ensemble NC with member IDs/shapes/weights, member/ensemble CSV and phase/PSD/reports.

Run:
    python 13_super_spheroid_interpolated_shapes_bulk.py; append --help for
    options.

Notes:
    Integrate each target shape over the common physical-radius PSD before bulk averaging.
    Example-only assertions are in tests/test_ensemble_exports.py; strict calculation checks
    remain enabled.

Retrieve shapes, integrate each PSD, then combine bulk optics.

    Edit ensemble_bulk_config.py for scientific inputs and output choices.
    Example-only assertions are in the test suite; strict calculation checks remain enabled.
"""
# ruff: noqa: E402
import argparse
from pathlib import Path
from local_environment import verify_local_import

verify_local_import()
from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.access.workflow import retrieve
from zju_scatt_interface.psd.analytical import lognormal_psd
from ensemble_bulk_config import FAMILY, WAVELENGTH_UM, COMMON, PSD_SETTINGS, CALCULATION_OPTIONS, EXAMPLES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Use a saved source catalog")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--no-track", action="store_true", help="Use cached sources without online usage tracking")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    settings = EXAMPLES["13"]
    root = args.output_dir or Path(__file__).resolve().parent / settings["output_dir"]
    manifest = root / "selection_manifest.jsonl"
    # CORE 1: select/download shared source dependencies; the interface checks completion.
    retrieved = retrieve(dict(particle_types=FAMILY, manifest=args.manifest,
        shapes=settings["shapes"], target_wavelengths=[WAVELENGTH_UM],
        refractive_index_parameters={FAMILY: COMMON}, apply_interpolation=False,
        output_dir=root / "sources", manifest_output=manifest, no_track=args.no_track), download=not args.list_only).single
    if args.list_only:
        return
    # CORE 2: one physical-radius PSD and the requested shape number fractions.
    psd = lognormal_psd(**PSD_SETTINGS)
    ensemble = WeightedShapeEnsemble.from_shapes(settings["shapes"], settings["weights"])
    # CORE 3: interpolate each target when needed, integrate its PSD, THEN average bulk results.
    calculation = compute_population(FAMILY,
        [item.target for item in retrieved.download_results], psd,
        wavelength=WAVELENGTH_UM, parameters=COMMON, shape_ensemble=ensemble,
        **CALCULATION_OPTIONS)
    # OUTPUT: validated NetCDF, member/ensemble CSV, phase/PSD CSV and diagnostic JSON.
    # Optional normalized L2 member exports are controlled in the configuration.
    outputs = calculation.save(root, component_name=settings["component_name"],
        source_manifest=str(manifest), size_distribution=psd,
        netcdf_path="application_outputs/bulk_optics_10_cm3.nc",
        include_members=True, l2_lognormal=settings["l2_lognormal"])
    for kind, path in outputs.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()
