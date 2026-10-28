"""Inspect registered particle profiles and the database layout without downloading optics.

Role:
    Production example

Inputs:
    Current registry and live listings, or --offline for registry-only inspection.

Outputs:
    Console metadata overview.

Run:
    python 01_database_overview.py; append --help for options.

Notes:
    Inspects or exports existing information; it does not run a new single-scattering solver.
"""

import argparse

from local_environment import verify_local_import

verify_local_import()

from zju_scatt_interface._version import __version__
from zju_scatt_interface.config.particles import list_particle_profiles
from zju_scatt_interface.access.client import ApiClient
from zju_scatt_interface.access.endpoints import ROOT_PREFIX
from zju_scatt_interface.errors import ScattError
from zju_scatt_interface.optics.refractive_index import RefractiveIndexTable
from zju_scatt_interface.optics.refractive_index import default_refractive_index_paths


def print_directory(client, prefix, indent=""):
    directories, files, _ = client.list_directory(prefix)
    for directory in directories:
        print(f"{indent}[DIR]  {directory.key[len(prefix):]}")
    for item in files:
        print(f"{indent}[FILE] {item.key[len(prefix):]} ({item.size:,} bytes)")
    if not directories and not files:
        print(f"{indent}(empty)")
    return directories


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Inspect installed profiles without contacting the database")
    args = parser.parse_args()
    print(f"ZJU-SCATT database overview (interface {__version__})", flush=True)
    if not args.offline:
        print("\nLIVE DATABASE DIRECTORIES (two levels; no data downloads)", flush=True)
        client = ApiClient(timeout=15, retries=0)
        try:
            directories = print_directory(client, ROOT_PREFIX)
            for directory in directories:
                print(f"\n{directory.key[len(ROOT_PREFIX):]}", flush=True)
                print_directory(client, directory.key, indent="  ")
        except ScattError as error:
            print(f"Live listing unavailable: {error}")
    print_profiles()


def print_profiles():
    """Print input contracts without requiring a live database connection."""
    profiles = list_particle_profiles()
    print(f"\nPARTICLE FAMILIES SUPPORTED BY THIS INTERFACE ({len(profiles)})")
    print("The following descriptions come from the installed package registry.")
    for number, profile in enumerate(profiles, start=1):
        print(f"\n{number}. {profile.display_name}")
        print(f"   particle_type: {profile.particle_type}")
        print(f"   Native database basis: {profile.data_structure.value}")
        wavelength = profile.parameter("wavelength")
        is_grid = profile.data_structure.value == "grid_based"
        if is_grid:
            print("   Wavelength: physical scaling and optional external index-table lookup;")
            print("               not a native database lookup coordinate.")
            if wavelength.minimum is not None and wavelength.maximum is not None:
                print(f"   Interface wavelength bounds: {wavelength.minimum:g} - {wavelength.maximum:g} {wavelength.unit} (also enforced with explicit indices)")
            else:
                print("   Interface wavelength bounds: finite and positive; no fixed spectral bounds.")
            try:
                tables = [RefractiveIndexTable.from_csv(path) for path in default_refractive_index_paths(profile.particle_type).values()]
                low = max(table.minimum_wavelength_um for table in tables)
                high = min(table.maximum_wavelength_um for table in tables)
                print(f"   Default material-table coverage: {low:g} - {high:g} um; no extrapolation.")
            except (OSError, ValueError) as error:
                print(f"   Default material-table coverage unavailable: {error}")
            print("   All modes require available native refractive-index and size coverage.")
        elif wavelength.minimum is not None and wavelength.maximum is not None:
            print(f"   Wavelength: {wavelength.minimum:g} - {wavelength.maximum:g} {wavelength.unit}")
        else:
            print("   Wavelength: limited by available source coverage")
        required = [p.name for p in profile.parameters if p.role.value == "required"]
        print(f"   Required inputs in default mode: {', '.join(required)}")
        if is_grid:
            indices = [p.name for p in profile.parameters if p.role.value == "optional" and "refractive_index" in p.name]
            print(f"   Explicit-index mode: also supply {', '.join(indices)}")
            print("   Supply the complete index set together; this bypasses the material tables.")
            print("   Wavelength remains the actual physical calculation wavelength in both modes.")
            if profile.particle_type == "super_spheroid":
                print("   Default table material: mineral dust; provide indices/custom table for other materials.")
                print('   Adapter example: adapter.resolve(files, wavelength=0.55, parameters={"roundness": 2.0, "aspect_ratio": 1.0, "mr": 1.5, "mi": 0.01})')
                print('   Scheme refractive_index: {"mode": "fixed", "real": 1.5, "imaginary": 0.01}')
            else:
                print('   Adapter index parameters: {"bc_mr": 1.75, "bc_mi": 0.65, "hygro_mr": 1.5, "hygro_mi": 0.01}; also supply df and vf.')
                print('   Scheme refractive_index: {"mode": "fixed", "black_carbon": {"real": 1.75, "imaginary": 0.65}, "hygroscopic": {"real": 1.5, "imaginary": 0.01}}')
        print(f"   Optical variables: {', '.join(profile.source_schema.required_optical_variables)}")
    print("\ncext: extinction cross section; ssa: single-scattering albedo;")
    print("g: asymmetry factor; sca_angle: scattering angle; pXX: phase-matrix elements.")
    print("This overview does not count all files or verify every parameter combination.")


if __name__ == "__main__":
    main()
