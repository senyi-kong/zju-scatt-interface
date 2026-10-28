"""io / l2 domain implementation."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zju_scatt_interface.io.paths import filesystem_path

VARIABLES = {
    "beta_ext": ("m^-1", "Extinction coefficient"),
    "ssa": ("1", "Single scattering albedo"),
    "g": ("1", "Asymmetry factor"),
    "wavelength": ("um", "Wavelength"),
    "mr": ("1", "Real part of refractive index"),
    "mi": ("1", "Imaginary part of refractive index"),
    "ssph_n": ("1", "Super-spheroid roundness parameter"),
    "ssph_asp": ("1", "Super-spheroid aspect ratio"),
    "rg": ("um", "Lognormal--Geometric mean radius"),
    "sigma": ("1", "Lognormal--Geometric standard deviation"),
    "sca_angle": ("degree", "Scattering angle"),
    **{
        name: ("1", f"Bulk phase matrix element {name}")
        for name in ("p11", "p12", "p22", "p33", "p43", "p44")
    },
}


def write_l2_lognormal(
    root,
    bulk,
    *,
    wavelength_um,
    parameters,
    rg_um,
    sigma_g,
    source_path,
    psd_metadata=None,
    data_version="v1.0",
    documentation_sources=None,
    interpolation_provenance=None,
):
    """Write a 1 cm^-3 normalized dust L2 product; input bulk may have any N.

    Input bulk coefficients must be m^-1 and number concentration cm^-3.
    beta_ext is divided by the input N; ssa/g and phase elements are unchanged.
    This matches the flat variable/dimension conventions of native L2 examples.
    Set documentation_sources to an iterable of Python source paths (or an empty
    iterable) to write accompanying documentation and production-code snapshots.
    source_path may be one path or a sequence of interpolation source paths.
    """
    import numpy as np
    from netCDF4 import Dataset

    concentration = float(bulk.number_concentration)
    if not math.isfinite(concentration) or concentration <= 0:
        raise ValueError("A positive bulk number concentration in cm^-3 is required")
    if bulk.metadata.get("number_concentration_output_unit") != "cm-3":
        raise ValueError("L2 normalization requires an explicitly recorded cm^-3 concentration")
    if bulk.metadata.get("bulk_coefficient_unit") != "m-1":
        raise ValueError("L2 output requires bulk coefficients in m^-1")
    angles = np.asarray(bulk.metadata["scattering_angles_degrees"], dtype=float)
    phase = np.asarray(bulk.phase_matrix, dtype=float)
    if angles.ndim != 1 or len(angles) < 2 or np.any(np.diff(angles) <= 0):
        raise ValueError("L2 output requires increasing scattering angles")
    if phase.shape != (len(angles), 4, 4) or not np.isfinite(phase).all():
        raise ValueError("L2 output requires finite full phase matrices")
    trapezoid = getattr(np, "trapezoid", None) or np.trapz
    radians = np.deg2rad(angles)
    normalization = 0.5 * trapezoid(phase[:, 0, 0] * np.sin(radians), radians)
    if not np.isclose(normalization, 1, rtol=0.005, atol=0):
        raise ValueError("L2 phase matrix must use the recorded 4pi normalization")
    if not (float(wavelength_um) > 0 and float(rg_um) > 0 and float(sigma_g) > 1):
        raise ValueError("Positive wavelength/radius and sigma_g > 1 are required")
    now = datetime.now(timezone.utc)
    date = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    from zju_scatt_interface.config.particles import normalize_parameter_name

    coordinates = {normalize_parameter_name(name): value for name, value in parameters.items()}
    n, asp = float(coordinates["roundness"]), float(coordinates["aspect_ratio"])
    mr, mi = (
        float(coordinates["refractive_index_real"]),
        float(coordinates["refractive_index_imaginary"]),
    )
    psd_token = f"psd_lognormal_normalized_veq_rg_{rg_um:.3f}_um_sigma_{sigma_g:.3f}"
    optical_token = f"wl_{wavelength_um:.3f}_um_ref_{mr:.3e}_{mi:.3e}"
    revision = f"{data_version}_{date}"
    path = (
        Path(root)
        / "L2_bulk_scattering_property"
        / "super_spheroid_dust"
        / "data"
        / psd_token
        / f"{optical_token}_{revision}"
        / f"L2_super_spheroid_dust_n_{n:.3f}_asp_{asp:.3f}_{optical_token}_{psd_token}_{revision}.nc"
    )
    local_path = filesystem_path(path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    sources = (
        [Path(source_path)]
        if isinstance(source_path, (str, Path))
        else list(dict.fromkeys(Path(p) for p in source_path))
    )
    if not sources:
        raise ValueError("L2 output requires at least one recorded source")
    institutions, levels, versions = set(), set(), set()
    for path_source in sources:
        with Dataset(str(filesystem_path(path_source))) as source:
            institution = str(getattr(source, "institution", ""))
            if not institution:
                raise ValueError("Source institution must be recorded for the L2 product")
            institutions.add(institution)
            levels.add(str(getattr(source, "data_level", "L1/L1.5")))
            versions.add(str(getattr(source, "data_version", "unknown")))
    institution = "; ".join(sorted(institutions))
    source_level, source_version = ", ".join(sorted(levels)), ", ".join(sorted(versions))
    source_text = "\n".join(str(p) for p in sources)
    scalars = {
        "beta_ext": float(bulk.extinction_coefficient) / concentration,
        "ssa": float(bulk.single_scattering_albedo),
        "g": float(bulk.asymmetry_factor),
        "wavelength": float(wavelength_um),
        "mr": mr,
        "mi": mi,
        "ssph_n": n,
        "ssph_asp": asp,
        "rg": float(rg_um),
        "sigma": float(sigma_g),
    }
    if not all(math.isfinite(value) for value in scalars.values()):
        raise ValueError("Nonfinite L2 scalar values")
    phase_indices = {
        "p11": (0, 0),
        "p12": (0, 1),
        "p22": (1, 1),
        "p33": (2, 2),
        "p43": (3, 2),
        "p44": (3, 3),
    }
    arrays = {
        "sca_angle": angles,
        **{name: phase[:, i, j] for name, (i, j) in phase_indices.items()},
    }
    temporary = local_path.with_suffix(".nc.part")
    with Dataset(str(temporary), "w", format="NETCDF4") as ds:
        ds.createDimension("sca_angle", len(angles))
        ds.setncatts(
            {
                "data_level": "L2",
                "data_version": data_version,
                "creation_date": now.isoformat().replace("+00:00", "Z"),
                "creator": "zju_scatt_interface",
                "institution": institution,
                "dataset_name": "super_spheroid_dust",
                "particle_shape": "super-spheroid",
                "description": "Number-normalized bulk optics for an explicitly specified super-spheroid dust model",
                "orientation_assumption": "random-oriented",
                "integration_method": "CDF-integrated PSD bins; conservative radius-grid remapping; sum of cross section times bin concentration",
                "psd": "number_lognormal",
                "psd_normalization": "normalized",
                "psd_description": f"n(r)=N/(sqrt(2*pi)*r*ln(sigma))*exp(-ln(r/rg)^2/(2*ln(sigma)^2)); volume-equivalent radius r in um; rg={rg_um:.17g} um; sigma={sigma_g:.17g}; normalized to N=1 cm^-3",
                "psd_reference_number_concentration_cm3": 1.0,
                "psd_rg_um": float(rg_um),
                "psd_sigma_g": float(sigma_g),
                "input_bulk_number_concentration_cm3": concentration,
                "concentration_scaling": "beta_ext(N)=beta_ext*N_cm3/(1 cm^-3); beta_sca=ssa*beta_ext; beta_abs=(1-ssa)*beta_ext",
                "psd_numerical_metadata_json": json.dumps(psd_metadata or {}, sort_keys=True),
                "phase_normalization": "0.5*integral_0^pi(p11*sin(theta)*dtheta)=1; dimensionless",
                "refractive_index_model": "explicit user-selected constant refractive index",
                "source_data": source_text,
                "source_data_level": source_level,
                "source_data_paths_json": json.dumps([str(p) for p in sources]),
                "source_data_version": source_version,
                "processing_type": "size_distribution_integration, number_concentration_normalization",
            }
        )
        if interpolation_provenance is not None:
            ds.setncattr(
                "interpolation_provenance_json",
                json.dumps(interpolation_provenance, sort_keys=True),
            )
        for name, (units, description) in VARIABLES.items():
            dims = ("sca_angle",) if name in arrays else ()
            variable = ds.createVariable(name, "f8", dims, fill_value=np.nan)
            variable.setncatts({"units": units, "description": description})
            variable[...] = arrays[name] if name in arrays else scalars[name]
    with Dataset(str(temporary)) as check:
        if check.groups or set(check.variables) != set(VARIABLES):
            raise RuntimeError("L2 flat schema verification failed")
        if not np.isclose(
            float(check.variables["beta_ext"][:]) * concentration, bulk.extinction_coefficient
        ):
            raise RuntimeError("L2 concentration scaling verification failed")
    os.replace(temporary, local_path)
    if documentation_sources is not None:
        _write_l2_documentation(
            local_path,
            source_path=source_text,
            parameters=parameters,
            psd_metadata=psd_metadata,
            concentration=concentration,
            documentation_sources=documentation_sources,
        )
    return local_path


def _lognormal_member_specs(calculation, psd):
    """Resolve targets and sources from recorded calculation data, never filenames."""
    from zju_scatt_interface.config.particles import normalize_parameter_name

    if calculation.particle_type != "super_spheroid":
        raise ValueError("Normalized lognormal L2 member export currently supports dust only")
    if (
        psd is None
        or psd.metadata.get("type") != "lognormal"
        or psd.size_definition != "volume_equivalent_sphere_radius"
    ):
        raise ValueError("L2 member export requires a volume-equivalent-radius lognormal PSD")
    rg, sigma = float(psd.metadata["rg_um"]), float(psd.metadata["sigma_g"])
    if not (math.isfinite(rg) and rg > 0 and math.isfinite(sigma) and sigma > 1):
        raise ValueError("L2 member export requires finite rg_um>0 and sigma_g>1")
    names = ("roundness", "aspect_ratio", "refractive_index_real", "refractive_index_imaginary")
    seen, specs = set(), []
    for member in calculation.members:
        parameters = {normalize_parameter_name(k): v for k, v in member.parameters.items()}
        target = member.interpolation_provenance.get("target_coordinates", {})
        for key, value in target.items():
            parameters.setdefault(normalize_parameter_name(key), value)
        if any(key not in parameters for key in names):
            raise ValueError("Missing explicit shape/RI coordinates for L2 member export")
        token = tuple(
            f"{float(parameters[key]):.3f}" if i < 2 else f"{float(parameters[key]):.3e}"
            for i, key in enumerate(names)
        )
        if token in seen:
            raise ValueError("L2 member targets collide at the standard filename precision")
        seen.add(token)
        neighbors = member.interpolation_provenance.get("neighbors", [])
        sources = list(
            dict.fromkeys(Path(node["source"]) for node in neighbors if node.get("source"))
        )
        if not sources or any(not p.is_file() for p in sources):
            raise ValueError(
                "L2 member export requires existing local sources recorded in interpolation provenance"
            )
        specs.append((member, parameters, sources))
    if not specs:
        raise ValueError("L2 member export requires calculated ensemble members")
    return rg, sigma, specs


def write_l2_lognormal_members(root, calculation, size_distribution):
    """Export each integrated dust member at N=1 cm^-3 in the native L2 schema.

    The ensemble average is not assigned a fictitious shape or exported as a
    fixed-shape L2 product. All interpolation source paths/weights are recorded.
    """
    rg, sigma, specs = _lognormal_member_specs(calculation, size_distribution)
    return [
        write_l2_lognormal(
            root,
            member.bulk,
            wavelength_um=calculation.wavelength_um,
            parameters=parameters,
            rg_um=rg,
            sigma_g=sigma,
            source_path=sources,
            psd_metadata=size_distribution.metadata,
            interpolation_provenance=member.interpolation_provenance,
        )
        for member, parameters, sources in specs
    ]


def _write_l2_documentation(
    path, *, source_path, parameters, psd_metadata, concentration, documentation_sources
):
    """Store assumptions and optional production-source snapshots beside L2 data."""
    import shutil

    import zju_scatt_interface.psd.analytical as analytical_psd

    documentation = path.parents[3] / "documentation"
    doc = documentation / "doc" / (path.stem + ".md")
    code = documentation / "src" / path.stem
    doc.parent.mkdir(parents=True, exist_ok=True)
    code.mkdir(parents=True, exist_ok=True)
    sources = [
        Path(__file__),
        Path(analytical_psd.__file__),
        *[Path(p) for p in documentation_sources],
    ]
    names = {}
    for source in sources:
        if source.name in names and names[source.name].resolve() != source.resolve():
            raise ValueError(f"Documentation snapshot filename collision: {source.name}")
        names[source.name] = source
    for name, source in names.items():
        destination = code / name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
    doc.write_text(
        f"# Normalized L2 lognormal dust optics\n\nData: `{path.name}`\n\n"
        f"Source: `{source_path}`\n\nParameters: `{dict(parameters)}`\n\n"
        f"PSD numerical metadata:\n```json\n{json.dumps(psd_metadata or {}, indent=2)}\n```\n\n"
        f"Physical size is volume-equivalent sphere radius. L2 beta_ext is m^-1 "
        f"at N=1 cm^-3; multiply by {concentration:g} for the input population. "
        "SSA, g and phase elements are concentration independent. "
        "Phase normalization: 0.5*integral(p11*sin(theta),0,pi)=1.\n\n"
        f"Production source snapshots: `../src/{path.stem}/`. "
        "The interface package and its dependencies are required to reproduce the calculation.\n",
        encoding="utf-8",
    )
    with (path.parents[4] / "update.log").open("a", encoding="utf-8") as stream:
        stream.write(
            f"{path.stem}: Generated normalized L2 lognormal dust optics; reference N=1 cm^-3, input N={concentration:g} cm^-3.\n"
        )
