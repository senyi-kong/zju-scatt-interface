#!/usr/bin/env python3
"""Requirement test for super-spheroid ice bulk optical workflows.

Scenarios:
1. Retrieve/download super-spheroid ice data at a target wavelength of 0.67 um,
   integrate over a user-defined unimodal log-normal particle size distribution,
   and plot the resulting bulk optical properties.
2. Retrieve/download super-spheroid ice data over 10-13 um, integrate over the
   same distribution, and plot absorption coefficient and bulk P11(180 deg)
   against wavelength.

The particle size distribution is intentionally defined in this script. The
database access, NetCDF optical-property loading, bulk integration, phase
matrix extraction, and plotting are performed through the zju-scatt interface.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Optional, Sequence

import zju_scatt_interface.access.client as _domain_access_client
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.retrieval as _domain_access_retrieval
import zju_scatt_interface.bulk.lowlevel as _domain_bulk_lowlevel
import zju_scatt_interface.optics.models as _domain_optics_models
import zju_scatt_interface.plotting.diagnostics as _domain_plotting_diagnostics

PARTICLE_TYPE = "super_spheroid_ice"
VISIBLE_TARGET_WAVELENGTH_UM = 0.67
INFRARED_WAVELENGTH_RANGE_UM = (10.0, 13.0)
GEOMETRIC_MEAN_DIAMETER_UM = 100.0
GEOMETRIC_STANDARD_DEVIATION = 1.8
TOTAL_NUMBER_CONCENTRATION = 1.0
DEFAULT_SHAPE_N = 2.0
DEFAULT_SHAPE_ASPECT_RATIO = 1.0


def lognormal_diameter_pdf(
    diameter_um: float,
    *,
    total_number: float = TOTAL_NUMBER_CONCENTRATION,
    geometric_mean_diameter_um: float = GEOMETRIC_MEAN_DIAMETER_UM,
    geometric_standard_deviation: float = GEOMETRIC_STANDARD_DEVIATION,
) -> float:
    """Return dN/dD for a unimodal log-normal diameter distribution."""
    if diameter_um <= 0.0:
        return 0.0
    log_sigma = math.log(geometric_standard_deviation)
    factor = total_number / (diameter_um * log_sigma * math.sqrt(2.0 * math.pi))
    exponent = -(
        math.log(diameter_um / geometric_mean_diameter_um) ** 2
    ) / (2.0 * log_sigma**2)
    return factor * math.exp(exponent)


def diameter_grid_and_jacobian(
    optics: _domain_optics_models.SingleParticleOptics,
) -> tuple[list[float], list[float]]:
    """Convert the loaded size grid to physical diameter and dD/dgrid."""
    if optics.size_unit == "um" and str(
        optics.metadata.get("size_definition", "")
    ) in {
        "volume_equivalent_sphere_radius",
        "maximum_dimension_radius",
    }:
        return [2.0 * radius for radius in optics.sizes], [
            2.0 for _ in optics.sizes
        ]
    size_dataset = str(optics.metadata.get("size_dataset", "")).casefold()
    wavelength_um = float(optics.metadata.get("wavelength_um", 1.0))
    if size_dataset.startswith("xsize"):
        # Compatibility fallback for older loaders that returned raw xsize.
        scale = wavelength_um / math.pi
        return [size * scale for size in optics.sizes], [scale for _ in optics.sizes]
    if "radius" in size_dataset or size_dataset == "reff":
        return [2.0 * size for size in optics.sizes], [2.0 for _ in optics.sizes]
    return list(optics.sizes), [1.0 for _ in optics.sizes]


def number_distribution_for_file(optics: _domain_optics_models.SingleParticleOptics) -> list[float]:
    """Build dN/dgrid on the ZJU-SCATT file's native size grid."""
    diameters_um, jacobian = diameter_grid_and_jacobian(optics)
    raw_distribution = [
        lognormal_diameter_pdf(diameter_um) * d_diameter_d_grid
        for diameter_um, d_diameter_d_grid in zip(diameters_um, jacobian)
    ]
    return _domain_bulk_lowlevel.normalize_number_distribution(
        optics.sizes,
        raw_distribution,
        TOTAL_NUMBER_CONCENTRATION,
        distribution_mode="density",
    )


def selected_shapes(args: argparse.Namespace) -> dict[str, float]:
    targets: dict[str, float] = {}
    if args.shape_n is not None:
        targets["n"] = args.shape_n
    if args.shape_aspect_ratio is not None:
        targets["asp"] = args.shape_aspect_ratio
    return targets


def downloaded_paths(result: _domain_access_models.RetrievalResult) -> list[Path]:
    paths = [
        item.target
        for item in result.download_results
        if item.status in {"downloaded", "skipped"}
    ]
    if paths:
        return paths
    raise RuntimeError(
        "No downloaded files are available. Check the retrieval filters, session, "
        "and --no-track setting."
    )


def retrieve_download(
    *,
    client: _domain_access_client.ApiClient,
    args: argparse.Namespace,
    output_dir: Path,
    target_wavelengths: Optional[Sequence[float]] = None,
    wavelength_range: Optional[Sequence[float]] = None,
    max_files: Optional[int] = None,
    manifest_output: Optional[Path] = None,
    operation_log: Optional[Path] = None,
) -> _domain_access_models.RetrievalResult:
    return _domain_access_retrieval.retrieve_sources(
        client=client,
        sources=f"Single_opt/{PARTICLE_TYPE}/",
        particle_types=PARTICLE_TYPE,
        wavelength_range=wavelength_range,
        wavelength_unit="um",
        target_wavelengths=target_wavelengths,
        target_wavelength_mode=args.visible_wavelength_mode if target_wavelengths else "interp",
        shapes=selected_shapes(args) or None,
        extension=("nc",),
        output_dir=output_dir,
        download=True,
        no_track=args.no_track,
        session=args.session,
        workers=args.workers,
        max_files=max_files,
        quiet=False,
        no_progress=args.no_progress,
        manifest_output=manifest_output,
        operation_log=operation_log,
    )


def calculate_bulk_for_files(
    paths: Sequence[Path],
    *,
    include_phase_matrix: bool,
    label: str,
) -> list[_domain_optics_models.BulkOptics]:
    results: list[_domain_optics_models.BulkOptics] = []
    for path in paths:
        print(f"Calculating bulk optics for {path}", file=sys.stderr)
        result = _domain_bulk_lowlevel.calculate_bulk_optics_from_file(
            path,
            number_distribution_for_file,
            include_phase_matrix=include_phase_matrix,
            distribution_mode="density",
            size_dataset="xsize_maxd",
            metadata={
                "particle_type": PARTICLE_TYPE,
                "scenario": label,
                "number_distribution": (
                    "unimodal log-normal diameter distribution; "
                    f"Dg={GEOMETRIC_MEAN_DIAMETER_UM:g} um, "
                    f"sigma_g={GEOMETRIC_STANDARD_DEVIATION:g}"
                ),
            },
        )
        results.append(result)
    results.sort(key=lambda item: float(item.metadata.get("wavelength_um", math.inf)))
    return results


def nearest_result(
    results: Sequence[_domain_optics_models.BulkOptics],
    target_wavelength_um: float,
) -> _domain_optics_models.BulkOptics:
    return min(
        results,
        key=lambda item: abs(float(item.metadata.get("wavelength_um", math.inf)) - target_wavelength_um),
    )


def temperature_key(result: _domain_optics_models.BulkOptics) -> str:
    temperature = result.metadata.get("temperature_k")
    if temperature is None:
        return "unknown"
    return f"{float(temperature):.0f}K"


def group_by_temperature(
    results: Sequence[_domain_optics_models.BulkOptics],
) -> dict[str, list[_domain_optics_models.BulkOptics]]:
    grouped: dict[str, list[_domain_optics_models.BulkOptics]] = {}
    for result in results:
        grouped.setdefault(temperature_key(result), []).append(result)
    for items in grouped.values():
        items.sort(key=lambda item: float(item.metadata.get("wavelength_um", math.inf)))
    return dict(sorted(grouped.items()))


def estimate_target_ref_from_results(
    results: Sequence[_domain_optics_models.BulkOptics],
    target_wavelength_um: float,
) -> tuple[float, float]:
    sorted_results = sorted(
        results,
        key=lambda item: float(item.metadata.get("wavelength_um", math.inf)),
    )
    for result in sorted_results:
        wavelength = float(result.metadata.get("wavelength_um", math.inf))
        if abs(wavelength - target_wavelength_um) < 1e-9:
            return float(result.metadata["ref_real"]), float(result.metadata["ref_imag"])

    lower: Optional[_domain_optics_models.BulkOptics] = None
    upper: Optional[_domain_optics_models.BulkOptics] = None
    for result in sorted_results:
        wavelength = float(result.metadata.get("wavelength_um", math.inf))
        if wavelength < target_wavelength_um:
            lower = result
        elif wavelength > target_wavelength_um and upper is None:
            upper = result
            break
    if lower is None or upper is None:
        nearest = nearest_result(sorted_results, target_wavelength_um)
        return float(nearest.metadata["ref_real"]), float(nearest.metadata["ref_imag"])

    lower_wavelength = float(lower.metadata["wavelength_um"])
    upper_wavelength = float(upper.metadata["wavelength_um"])
    fraction = (target_wavelength_um - lower_wavelength) / (
        upper_wavelength - lower_wavelength
    )
    lower_ref = (float(lower.metadata["ref_real"]), float(lower.metadata["ref_imag"]))
    upper_ref = (float(upper.metadata["ref_real"]), float(upper.metadata["ref_imag"]))
    return (
        lower_ref[0] + fraction * (upper_ref[0] - lower_ref[0]),
        lower_ref[1] + fraction * (upper_ref[1] - lower_ref[1]),
    )


def interpolated_scalar_result(
    results: Sequence[_domain_optics_models.BulkOptics],
    target_wavelength_um: float,
    *,
    mode: str,
) -> _domain_optics_models.BulkOptics:
    """Select or interpolate scalar bulk quantities for a target wavelength."""
    sorted_results = sorted(
        results,
        key=lambda item: float(item.metadata.get("wavelength_um", math.inf)),
    )
    if mode == "nearest":
        closest = nearest_result(sorted_results, target_wavelength_um)
        metadata = dict(closest.metadata)
        metadata["retrieval_mode"] = "nearest"
        return _domain_optics_models.BulkOptics(
            extinction_coefficient=closest.extinction_coefficient,
            scattering_coefficient=closest.scattering_coefficient,
            absorption_coefficient=closest.absorption_coefficient,
            single_scattering_albedo=closest.single_scattering_albedo,
            asymmetry_factor=closest.asymmetry_factor,
            phase_matrix=None,
            number_concentration=closest.number_concentration,
            size_count=closest.size_count,
            metadata=metadata,
        )

    for result in sorted_results:
        wavelength = float(result.metadata.get("wavelength_um", math.inf))
        if abs(wavelength - target_wavelength_um) < 1e-9:
            return result
    target_ref = estimate_target_ref_from_results(sorted_results, target_wavelength_um)
    distances = []
    for result in sorted_results:
        ref_point = (
            float(result.metadata["ref_real"]),
            float(result.metadata["ref_imag"]),
        )
        distance = math.hypot(ref_point[0] - target_ref[0], ref_point[1] - target_ref[1])
        if distance <= 1e-15:
            return result
        distances.append((result, distance))
    weights = [(result, 1.0 / distance) for result, distance in distances]
    total_weight = sum(weight for _result, weight in weights)

    def interp(name: str) -> Optional[float]:
        values = [
            (getattr(result, name), weight)
            for result, weight in weights
            if getattr(result, name) is not None
        ]
        if not values:
            return None
        available_weight = sum(weight for _value, weight in values)
        return sum(float(value) * weight for value, weight in values) / available_weight

    metadata = dict(sorted_results[0].metadata)
    metadata.update(
        {
            "wavelength_um": target_wavelength_um,
            "ref_real": target_ref[0],
            "ref_imag": target_ref[1],
            "interpolation": (
                "inverse-distance interpolation of bulk scalar quantities "
                "in refractive-index (n,k) space"
            ),
            "retrieval_mode": "interp",
        }
    )
    return _domain_optics_models.BulkOptics(
        extinction_coefficient=interp("extinction_coefficient"),
        scattering_coefficient=interp("scattering_coefficient"),
        absorption_coefficient=interp("absorption_coefficient"),
        single_scattering_albedo=interp("single_scattering_albedo"),
        asymmetry_factor=interp("asymmetry_factor"),
        phase_matrix=None,
        number_concentration=sum(
            result.number_concentration * weight for result, weight in weights
        )
        / total_weight,
        size_count=max(result.size_count for result in sorted_results),
        metadata=metadata,
    )


def write_summary_csv(path: Path, results: Sequence[_domain_optics_models.BulkOptics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scenario",
        "temperature_k",
        "wavelength_um",
        "ref_real",
        "ref_imag",
        "number_concentration",
        "extinction_coefficient",
        "scattering_coefficient",
        "absorption_coefficient",
        "single_scattering_albedo",
        "asymmetry_factor",
        "p11_180",
        "matched_angle",
        "source_file",
        "retrieval_mode",
        "interpolation",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            p11_180 = None
            matched_angle = None
            if result.phase_matrix is not None:
                p11_180, matched_angle = _domain_bulk_lowlevel.bulk_phase_matrix_element(result, angle=180.0)
            writer.writerow(
                {
                    "scenario": result.metadata.get("scenario"),
                    "temperature_k": result.metadata.get("temperature_k"),
                    "wavelength_um": result.metadata.get("wavelength_um"),
                    "ref_real": result.metadata.get("ref_real"),
                    "ref_imag": result.metadata.get("ref_imag"),
                    "number_concentration": result.number_concentration,
                    "extinction_coefficient": result.extinction_coefficient,
                    "scattering_coefficient": result.scattering_coefficient,
                    "absorption_coefficient": result.absorption_coefficient,
                    "single_scattering_albedo": result.single_scattering_albedo,
                    "asymmetry_factor": result.asymmetry_factor,
                    "p11_180": p11_180,
                    "matched_angle": matched_angle,
                    "source_file": result.metadata.get("source_file"),
                    "retrieval_mode": result.metadata.get("retrieval_mode"),
                    "interpolation": result.metadata.get("interpolation"),
                }
            )


def write_summary_json(path: Path, results: Sequence[_domain_optics_models.BulkOptics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([result.to_dict() for result in results], indent=2) + "\n",
        encoding="utf-8",
    )


def write_requirement_operation_log(
    path: Path,
    *,
    args: argparse.Namespace,
    visible_target_results: Sequence[_domain_optics_models.BulkOptics],
    infrared_results: Sequence[_domain_optics_models.BulkOptics],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        stream.write("Super-spheroid ice bulk-optics requirement operation log\n")
        stream.write("\nScenario 1: target wavelength retrieval and bulk interpolation\n")
        stream.write(f"  Target wavelength: {args.visible_wavelength:g} um\n")
        stream.write(f"  Target wavelength mode: {args.visible_wavelength_mode}\n")
        for result in visible_target_results:
            interpolation_text = result.metadata.get("interpolation")
            stream.write(f"  Temperature: {temperature_key(result)}\n")
            stream.write(
                "    Bulk interpolation applied: "
                f"{'yes' if interpolation_text else 'no'}\n"
            )
            stream.write(
                "    Bulk interpolation basis: "
                f"{'refractive_index_nk' if interpolation_text else 'none'}\n"
            )
            if interpolation_text:
                stream.write(f"    Processing: {interpolation_text}\n")
            stream.write(
                "    Absorption coefficient: "
                f"{result.absorption_coefficient}\n"
            )

        stream.write("\nScenario 2: wavelength-range bulk optics\n")
        stream.write(
            f"  Wavelength range: {args.infrared_range[0]:g}-"
            f"{args.infrared_range[1]:g} um\n"
        )
        for temp, temp_results in group_by_temperature(infrared_results).items():
            wavelengths = [
                float(result.metadata.get("wavelength_um", math.nan))
                for result in temp_results
            ]
            stream.write(f"  Temperature: {temp}\n")
            stream.write(
                "    Wavelengths processed: "
                + ", ".join(f"{value:g} um" for value in wavelengths)
                + "\n"
            )
            stream.write("    Plot grouping: separate temperature figure\n")

        stream.write("\nStatus\n")
        stream.write("  BULK OPTICS REQUIREMENT PROCESSING SUCCESSFUL\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the two super-spheroid ice ZJU-SCATT requirement scenarios."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("super_spheroid_ice_requirement_results"),
        help="Directory for manifests, logs, summaries, and plots",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("super_spheroid_ice_requirement_data"),
        help="Directory for downloaded ZJU-SCATT NetCDF files",
    )
    parser.add_argument("--visible-wavelength", type=float, default=VISIBLE_TARGET_WAVELENGTH_UM)
    parser.add_argument(
        "--infrared-range",
        nargs=2,
        type=float,
        metavar=("MIN_UM", "MAX_UM"),
        default=INFRARED_WAVELENGTH_RANGE_UM,
    )
    parser.add_argument("--shape-n", type=float, default=DEFAULT_SHAPE_N)
    parser.add_argument("--shape-aspect-ratio", type=float, default=DEFAULT_SHAPE_ASPECT_RATIO)
    parser.add_argument(
        "--visible-wavelength-mode",
        choices=("interp", "nearest"),
        default="interp",
        help=(
            "For the 0.67 um target, interpolate by refractive-index (n,k) "
            "distance or use nearest wavelength data."
        ),
    )
    parser.add_argument(
        "--visible-max-files",
        type=int,
        default=None,
        help="Limit visible files; default keeps all selected temperature groups",
    )
    parser.add_argument(
        "--infrared-max-files",
        type=int,
        default=None,
        help="Limit infrared files; default downloads all matches for the filters",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--session", help="Website download-tracking session token")
    parser.add_argument("--no-track", action="store_true", help="Bypass website tracking")
    parser.add_argument("--no-progress", action="store_true", help="Disable download progress")
    parser.add_argument("--skip-plots", action="store_true", help="Calculate only")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--insecure", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.data_dir.mkdir(parents=True, exist_ok=True)

    client = _domain_access_client.ApiClient(
        timeout=args.timeout,
        retries=args.retries,
        insecure=args.insecure,
    )

    print("Scenario 1: target wavelength 0.67 um", file=sys.stderr)
    visible_retrieval = retrieve_download(
        client=client,
        args=args,
        output_dir=args.data_dir / "scenario_1_visible",
        target_wavelengths=[args.visible_wavelength],
        max_files=args.visible_max_files,
        manifest_output=args.output_dir / "scenario_1_visible_manifest.csv",
        operation_log=args.output_dir / "scenario_1_visible_operation.log",
    )
    visible_results = calculate_bulk_for_files(
        downloaded_paths(visible_retrieval),
        include_phase_matrix=False,
        label="scenario_1_visible_0.67um",
    )
    visible_target_results = [
        interpolated_scalar_result(
            temp_results,
            args.visible_wavelength,
            mode=args.visible_wavelength_mode,
        )
        for temp_results in group_by_temperature(visible_results).values()
    ]

    if not args.skip_plots:
        for result in visible_target_results:
            temp = temperature_key(result)
            _domain_plotting_diagnostics.plot_optical_properties(
                result,
                output=args.output_dir / f"scenario_1_visible_bulk_optics_{temp}.png",
                title=(
                    f"{PARTICLE_TYPE} bulk optics at "
                    f"{args.visible_wavelength:g} um, {temp}"
                ),
                close=True,
            )

    print("Scenario 2: wavelength range 10-13 um", file=sys.stderr)
    infrared_retrieval = retrieve_download(
        client=client,
        args=args,
        output_dir=args.data_dir / "scenario_2_infrared",
        wavelength_range=args.infrared_range,
        max_files=args.infrared_max_files,
        manifest_output=args.output_dir / "scenario_2_infrared_manifest.csv",
        operation_log=args.output_dir / "scenario_2_infrared_operation.log",
    )
    infrared_results = calculate_bulk_for_files(
        downloaded_paths(infrared_retrieval),
        include_phase_matrix=True,
        label="scenario_2_infrared_10_13um",
    )

    if not args.skip_plots:
        for temp, temp_results in group_by_temperature(infrared_results).items():
            _domain_plotting_diagnostics.plot_bulk_wavelength_series(
                temp_results,
                output=(
                    args.output_dir
                    / f"scenario_2_absorption_p11_180_by_wavelength_{temp}.png"
                ),
                phase_angle=180.0,
                phase_row=0,
                phase_column=0,
                title=(
                    f"{PARTICLE_TYPE}: absorption and bulk P11(180 deg), "
                    f"{args.infrared_range[0]:g}-{args.infrared_range[1]:g} um, {temp}"
                ),
                close=True,
            )

    all_results = [*visible_results, *visible_target_results, *infrared_results]
    write_summary_csv(args.output_dir / "bulk_optics_requirement_summary.csv", all_results)
    write_summary_json(args.output_dir / "bulk_optics_requirement_summary.json", all_results)
    write_requirement_operation_log(
        args.output_dir / "bulk_optics_requirement_operation.log",
        args=args,
        visible_target_results=visible_target_results,
        infrared_results=infrared_results,
    )

    print(f"Outputs written to: {args.output_dir.resolve()}", file=sys.stderr)
    print("SUPER-SPHEROID ICE REQUIREMENT TEST SUCCESSFUL", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
