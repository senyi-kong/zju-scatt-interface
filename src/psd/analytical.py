"""psd / analytical domain implementation."""

from __future__ import annotations

import math

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.psd.models import SizeDistribution, _bin_edges


def radius_moments(psd):
    """Realized moments of the discrete per-bin population used by the engine."""
    moments = {j: math.fsum(n * r**j for r, n in zip(psd.size_um, psd.dndr_cm3)) for j in range(5)}
    effective = moments[3] / moments[2]
    mu = math.fsum(n * math.log(r) for r, n in zip(psd.size_um, psd.dndr_cm3)) / moments[0]
    return {
        "realized_number_mean_radius_um": moments[1] / moments[0],
        "realized_effective_radius_um": effective,
        "realized_effective_variance": max(0.0, moments[4] * moments[2] / moments[3] ** 2 - 1),
        "realized_geometric_mean_radius_um": math.exp(mu),
        "realized_geometric_standard_deviation": math.exp(
            math.sqrt(
                max(
                    0.0,
                    math.fsum(
                        n * (math.log(r) - mu) ** 2 for r, n in zip(psd.size_um, psd.dndr_cm3)
                    )
                    / moments[0],
                )
            )
        ),
        "effective_radius_definition": "M3/M2 on the physical volume-equivalent radius coordinate",
    }


def _gamma_probabilities(a, x):
    """Regularized lower/upper incomplete gamma; series and continued fraction.

    Evaluate the small tail directly to avoid cancellation in narrow tail bins.
    Uses only the standard library; the distribution needs NumPy for its grid,
    just like the existing lognormal constructor, but does not require SciPy.
    """
    if x <= 0:
        return 0.0, 1.0
    if math.isinf(x):
        return 1.0, 0.0
    log_prefactor = a * math.log(x) - x - math.lgamma(a)
    prefactor = math.exp(log_prefactor)
    if x < a + 1:
        term = total = 1 / a
        for i in range(1, 10001):
            term *= x / (a + i)
            total += term
            if abs(term) <= abs(total) * 2e-15:
                p = min(1.0, max(0.0, total * prefactor))
                return p, 1 - p
    else:
        tiny = 1e-300
        b = x + 1 - a
        c, d = 1 / tiny, 1 / b
        value = d
        for i in range(1, 10001):
            coefficient = -i * (i - a)
            b += 2
            d = coefficient * d + b
            if abs(d) < tiny:
                d = tiny
            c = b + coefficient / c
            if abs(c) < tiny:
                c = tiny
            d = 1 / d
            change = d * c
            value *= change
            if abs(change - 1) <= 2e-15:
                q = min(1.0, max(0.0, value * prefactor))
                return 1 - q, q
    raise ValueError(
        "Gamma probability calculation did not converge; use a less extreme effective_variance"
    )


def _gamma_quantile(a, probability):
    if (math.log(probability) + math.lgamma(a + 1)) / a < -740:
        raise ValueError(
            "Gamma lower quantile is below floating-point radius resolution; supply radius_range_um explicitly"
        )
    lower, upper = 0.0, max(1.0, a)
    while _gamma_probabilities(a, upper)[0] < probability:
        upper *= 2
    for _ in range(2048):
        midpoint = (lower + upper) / 2
        if midpoint == lower or midpoint == upper:
            break
        if _gamma_probabilities(a, midpoint)[0] < probability:
            lower = midpoint
        else:
            upper = midpoint
        if lower > 0 and upper - lower < 2e-14 * lower:
            break
    return (lower + upper) / 2


def gamma_radius_bounds(effective_radius_um, effective_variance):
    """Finite numerical bounds retaining all but 1e-8 probability per tail."""
    radius, variance = _gamma_parameters(effective_radius_um, effective_variance)
    a, theta = 1 / variance - 2, radius * variance
    return theta * _gamma_quantile(a, 1e-8), theta * _gamma_quantile(a, 1 - 1e-8)


def _gamma_parameters(effective_radius_um, effective_variance):
    radius, variance = float(effective_radius_um), float(effective_variance)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("effective_radius_um must be finite and positive")
    if not math.isfinite(variance) or not 0 < variance < 0.5:
        raise ValueError("effective_variance must satisfy 0 < effective_variance < 0.5")
    return radius, variance


@_registration_required
def gamma_psd(
    effective_radius_um,
    effective_variance,
    number_concentration_cm3=1.0,
    *,
    radius_range_um=None,
    bins=400,
    normalization="preserve",
):
    """CDF-integrated Hansen-Travis gamma number PSD on physical radius bins.

    n(r)=N/[Gamma(a)*theta**a]*r**(a-1)*exp(-r/theta), where
    a=1/v_eff-2 and theta=r_eff*v_eff. The number-mean radius is
    r_eff*(1-2*v_eff), so r_eff must never be called the number-mean radius.
    'preserve' retains parent population within bounds; 'renormalize' makes
    the finite conditional distribution sum to the supplied number concentration.
    """
    import numpy as np

    radius, variance = _gamma_parameters(effective_radius_um, effective_variance)
    concentration = float(number_concentration_cm3)
    if not math.isfinite(concentration) or concentration <= 0:
        raise ValueError("number_concentration_cm3 must be finite and positive")
    if isinstance(bins, bool) or int(bins) != bins or bins < 3:
        raise ValueError("bins must be an integer >= 3")
    if normalization not in {"preserve", "renormalize"}:
        raise ValueError("normalization must be 'preserve' or 'renormalize'")
    bounds = gamma_radius_bounds(radius, variance) if radius_range_um is None else radius_range_um
    if len(bounds) != 2:
        raise ValueError("radius_range_um requires two bounds")
    lower, upper = map(float, bounds)
    if not (math.isfinite(lower) and math.isfinite(upper) and 0 < lower < upper):
        raise ValueError("radius_range_um must be finite, positive and increasing")
    centers = np.geomspace(lower, upper, int(bins))
    edges = _bin_edges(centers)
    centers = lower + (centers - edges[0]) * ((upper - lower) / (edges[-1] - edges[0]))
    edges = _bin_edges(centers)
    a, theta = 1 / variance - 2, radius * variance
    probabilities = [_gamma_probabilities(a, edge / theta) for edge in edges]
    mass = [
        max(0.0, q0 - q1 if left / theta >= a + 1 else p1 - p0)
        for left, (p0, q0), (p1, q1) in zip(edges, probabilities, probabilities[1:])
    ]
    retained = math.fsum(mass)
    if retained <= 0:
        raise ValueError("No numerically resolved gamma population within radius_range_um")
    factor = concentration / retained if normalization == "renormalize" else concentration
    metadata = {
        "type": "gamma",
        "effective_radius_um": radius,
        "effective_variance": variance,
        "gamma_shape": a,
        "gamma_scale_um": theta,
        "parent_number_mean_radius_um": radius * (1 - 2 * variance),
        "requested_number_concentration_cm3": concentration,
        "radius_bin_edges_um": [float(edges[0]), float(edges[-1])],
        "retained_untruncated_gamma_probability": retained,
        "omitted_tail_probability": max(0.0, 1 - retained),
        "normalization": normalization,
        "bins": int(bins),
    }
    psd = SizeDistribution(
        centers.tolist(), [m * factor for m in mass], metadata=metadata, source="gamma_psd"
    )
    return SizeDistribution(
        psd.size_um, psd.dndr_cm3, metadata={**metadata, **radius_moments(psd)}, source=psd.source
    )


def _positive_parameter(value, name):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


@_registration_required
def lognormal_psd(
    rg_um,
    sigma_g,
    number_concentration_cm3=1.0,
    *,
    radius_range_um=None,
    bins=400,
    normalization="preserve",
):
    """CDF-integrated bin counts on a volume-equivalent radius grid.

    rg_um is the parent geometric mean *radius*. Without explicit bounds the
    finite grid spans +/- four logarithmic standard deviations. 'preserve'
    retains only the parent population within the bounds; 'renormalize' makes
    the finite distribution sum to the supplied concentration. Never shifts rg.
    """
    import numpy as np

    rg, sigma = _positive_parameter(rg_um, "rg_um"), _positive_parameter(sigma_g, "sigma_g")
    concentration = _positive_parameter(number_concentration_cm3, "number_concentration_cm3")
    if sigma <= 1:
        raise ValueError("sigma_g must exceed 1")
    if isinstance(bins, bool) or int(bins) != bins or bins < 3:
        raise ValueError("bins must be an integer >= 3")
    if normalization not in {"preserve", "renormalize"}:
        raise ValueError("normalization must be 'preserve' or 'renormalize'")
    width = 4 * math.log(sigma)
    bounds = (
        radius_range_um
        if radius_range_um is not None
        else (rg * math.exp(-width), rg * math.exp(width))
    )
    if len(bounds) != 2:
        raise ValueError("radius_range_um requires two bounds")
    lower, upper = (_positive_parameter(x, "radius_range_um") for x in bounds)
    if lower >= upper:
        raise ValueError("radius_range_um must be increasing")
    centers = np.geomspace(lower, upper, int(bins))
    edges = _bin_edges(centers)
    # The integrator defines bin edges using arithmetic midpoints. Fit those
    # edges, rather than merely fitting sample centers, into the physical range.
    centers = lower + (centers - edges[0]) * ((upper - lower) / (edges[-1] - edges[0]))
    edges = _bin_edges(centers)
    log_sigma = math.log(sigma)

    def interval_mass(a, b):
        za = math.log(a / rg) / (math.sqrt(2) * log_sigma)
        zb = math.log(b / rg) / (math.sqrt(2) * log_sigma)
        return (
            0.5 * (math.erfc(za) - math.erfc(zb))
            if za >= 0
            else 0.5 * (math.erfc(-zb) - math.erfc(-za))
        )

    masses = np.array([interval_mass(a, b) for a, b in zip(edges, edges[1:])])
    retained = float(masses.sum())
    if retained <= 0:
        raise ValueError("No numerically resolved lognormal population within radius_range_um")
    counts = masses * concentration / (retained if normalization == "renormalize" else 1)
    mu = float(np.sum(counts * np.log(centers)) / counts.sum())
    metadata = {
        "type": "lognormal",
        "rg_um": rg,
        "sigma_g": sigma,
        "requested_number_concentration_cm3": concentration,
        "radius_bin_edges_um": [float(edges[0]), float(edges[-1])],
        "retained_untruncated_lognormal_probability": retained,
        "omitted_tail_probability": max(0.0, 1 - retained),
        "normalization": normalization,
        "bins": int(bins),
        "realized_geometric_mean_radius_um": math.exp(mu),
        "realized_geometric_standard_deviation": math.exp(
            math.sqrt(float(np.sum(counts * (np.log(centers) - mu) ** 2) / counts.sum()))
        ),
    }
    psd = SizeDistribution(
        centers.tolist(), counts.tolist(), metadata=metadata, source="lognormal_psd"
    )
    return SizeDistribution(
        psd.size_um, psd.dndr_cm3, metadata={**metadata, **radius_moments(psd)}, source=psd.source
    )
