"""Application-neutral fixed-population spectrum preparation and species labels."""

from __future__ import annotations

import json
from pathlib import Path

from zju_scatt_interface.io.native import _increasing

AEROSOL_NAMES = {
    "super_spheroid": "dust",
    "encapsulated_fractal_aggregates_black_carbon": "black_carbon",
    "coated_super_spheroid_seasalt": "sea_salt",
    "sphere_sulfate": "sulfate",
    "sphere_nitrate": "nitrate",
    "sphere_organic_carbon": "organic_carbon",
}

HYDROMETEOR_NAMES = {
    "sphere_water_cloud": "water_cloud_zju_gamma",
    "super_spheroid_ice": "ice_cloud_zju_super_spheroid",
}


def input_spectrum(data):
    """Read calculated results, or a canonical NetCDF plus sibling report.json."""
    import numpy as np

    if isinstance(data, (str, Path)):
        from netCDF4 import Dataset

        from zju_scatt_interface.io.canonical import validate_file

        path = Path(data)
        validate_file(path).require_valid()
        report = json.loads(path.with_name("report.json").read_text(encoding="utf-8"))
        wavelengths = tuple(report["wavelengths_um"])
        records = {}
        with Dataset(path) as nc:
            if set(nc.groups) != set(report["species"]):
                raise ValueError("Bulk file and report have different species")
            for family, group in nc.groups.items():
                if tuple(group["wavelength"][:]) != wavelengths:
                    raise ValueError("Bulk file and report have different wavelengths/order")
                psd = report["species"][family]["psd"]
                for variable, field in (("psd_size", "size"), ("psd_dndr", "dndr")):
                    if not np.array_equal(group[variable][:], psd[field]):
                        raise ValueError(f"Bulk file and report disagree on {family} PSD")
                if "p11" not in group.variables:
                    raise ValueError(
                        "Application export requires bulk P11; enable include_phase_matrix"
                    )
                records[family] = [
                    {
                        "ext": float(group["beta_ext"][i]),
                        "ssa": float(group["ssa"][i]),
                        "g": float(group["g"][i]),
                        "number": float(group["number_concentration"][i]),
                        "angles": np.asarray(group["sca_angle"][:]),
                        "p11": np.asarray(group["p11"][i]),
                    }
                    for i in range(len(wavelengths))
                ]
        return wavelengths, records, report
    wavelengths, records = tuple(data.scheme.wavelengths_um), {}
    for family, calculations in data.scheme.components.items():
        if tuple(c.wavelength_um for c in calculations) != wavelengths:
            raise ValueError(f"Incomplete/reordered spectrum for {family}")
        records[family] = []
        for calculation in calculations:
            bulk = calculation.bulk
            if bulk.phase_matrix is None:
                raise ValueError("Application export requires include_phase_matrix=True")
            records[family].append(
                {
                    "ext": bulk.extinction_coefficient,
                    "ssa": bulk.single_scattering_albedo,
                    "g": bulk.asymmetry_factor,
                    "number": bulk.number_concentration,
                    "angles": np.asarray(bulk.metadata["scattering_angles_degrees"]),
                    "p11": np.asarray(bulk.phase_matrix)[:, 0, 0],
                }
            )
    return wavelengths, records, data.report


def characters(strings, width):
    import numpy as np

    if any(len(s) > width or not s.isascii() for s in strings):
        raise ValueError(f"Output strings must be ASCII and no longer than {width} characters")
    return np.asarray([list(s.ljust(width)) for s in strings], dtype="S1")


def normalized_bulk_coefficients(bulk, norm):
    import math

    from zju_scatt_interface.bulk.quality import validate_bulk_optics

    report = validate_bulk_optics(bulk)
    if not report.passed:
        raise ValueError(f"invalid bulk optics: {report.errors}")
    if any(
        v is None
        for v in (
            bulk.extinction_coefficient,
            bulk.scattering_coefficient,
            bulk.absorption_coefficient,
        )
    ):
        raise ValueError("bulk extinction, scattering and absorption are required")
    if norm is None or not math.isfinite(float(norm)) or norm <= 0:
        raise ValueError("a finite positive mass or number normalization is required")
    return tuple(
        float(value) / norm
        for value in (
            bulk.extinction_coefficient,
            bulk.scattering_coefficient,
            bulk.absorption_coefficient,
        )
    )


def scalar_phase_projection(
    angles_degrees,
    p11,
    *,
    convention,
    max_moments=128,
    quadrature_points=512,
    hemisphere_points=32,
    normalization_tolerance=0.01,
):
    """Project one normalized scalar P11 onto native phase representations.

    Linear interpolation in cos(theta), Gauss-Legendre integration. Input must
    satisfy 0.5*integral(P11 dmu)=1; it is never silently renormalized. Increase
    angular resolution and quadrature for sharply peaked scattering.
    RTTOV BPR uses the Chou double-hemisphere/azimuth integral, not hemispheric
    backscatter or (1-g)/2. CRTM output is scalar (n_Phase_Elements=1), packs
    untruncated coefficients for its 4/6/8/16-stream sets, with no delta scaling.
    Vector/generalized spherical coefficients must be supplied separately.
    """
    import numpy as np
    from numpy.polynomial.legendre import leggauss, legvander

    angles = np.asarray(angles_degrees, dtype=float)
    phase = np.asarray(p11, dtype=float)
    _increasing(angles, "phase angles")
    if angles[0] != 0 or angles[-1] != 180 or phase.shape != angles.shape:
        raise ValueError("P11 must match an angle grid spanning 0..180 degrees")
    if not np.isfinite(phase).all() or np.any(phase < 0):
        raise ValueError("P11 must be finite and nonnegative")
    if convention not in {"legendre", "crtm_streams"}:
        raise ValueError("Unknown scalar phase coefficient convention")
    degree = max_moments if convention == "legendre" else 16
    if not isinstance(degree, int) or degree < 0 or quadrature_points < max(32, 2 * degree + 1):
        raise ValueError("quadrature_points must be >= max(32, 2*degree+1)")
    if hemisphere_points < 4 or not 0 < normalization_tolerance < 1:
        raise ValueError("invalid hemisphere quadrature or normalization tolerance")
    mu, weights = leggauss(quadrature_points)
    grid = np.cos(np.deg2rad(angles))[::-1]
    sampled = np.interp(mu, grid, phase[::-1])
    moments = (weights * sampled) @ legvander(mu, degree) / 2
    if abs(moments[0] - 1) > normalization_tolerance:
        raise ValueError(f"P11 is not normalized to 4pi: half-integral={moments[0]:.8g}")
    expansion = (2 * np.arange(degree + 1) + 1) * moments
    if convention == "crtm_streams":
        packed = np.zeros(39)
        for offset, nstreams in ((0, 4), (5, 6), (12, 8), (21, 16)):
            packed[offset : offset + nstreams + 1] = expansion[: nstreams + 1] / 2
        return {"pcoeff": packed, "g": float(moments[1] / moments[0])}
    nodes, hw = leggauss(hemisphere_points)
    upper, lower = (nodes + 1) / 2, (nodes - 1) / 2
    azimuth = np.cos(2 * np.pi * np.arange(4 * hemisphere_points) / (4 * hemisphere_points))
    costheta = (
        upper[:, None, None] * lower[None, :, None]
        + np.sqrt(1 - upper**2)[:, None, None] * np.sqrt(1 - lower**2)[None, :, None] * azimuth
    )
    averaged = np.interp(costheta, grid, phase[::-1]).mean(axis=-1)
    bpr = float(np.einsum("i,ij,j->", hw / 2, averaged, hw / 2) / 2)
    return {"LEGCOEF": expansion, "NMOM": degree, "BPR": bpr, "normalization": float(moments[0])}
