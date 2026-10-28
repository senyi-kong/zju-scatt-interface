"""Built-in analytical PSD option validation and source-coverage policies."""

import math

from zju_scatt_interface.psd.analytical import gamma_psd, gamma_radius_bounds, lognormal_psd
from zju_scatt_interface.psd.models import SizeDistribution


def analytical_distribution(config, context):
    lower, upper = context.lower_um, context.upper_um
    concentration = context.concentration_cm3
    conditional_reference = context.conditional_reference
    config = dict(config)
    if context.reference:
        config["number_concentration_cm3"] = concentration
    kind = config.get("type", "lognormal")
    fields = {
        "lognormal": {"rg_um", "sigma_g"},
        "gamma": {"effective_radius_um", "effective_variance"},
    }
    if kind not in fields:
        raise ValueError(f"Unsupported analytical PSD type: {kind}")
    allowed = {
        "type",
        "number_concentration_cm3",
        "radius_range_um",
        "bins",
        "normalization",
        "size_definition",
        "interpretation",
    } | fields[kind]
    if set(config) - allowed:
        raise ValueError(f"Unknown {kind} PSD options: {set(config) - allowed}")
    if (
        config.get("size_definition", "volume_equivalent_sphere_radius")
        != "volume_equivalent_sphere_radius"
    ):
        raise ValueError("Analytical PSDs must use physical volume-equivalent radius")
    missing = fields[kind] - set(config)
    if missing:
        raise ValueError(f"{kind} PSD requires {sorted(missing)}")
    bounds = config.get("radius_range_um")
    normalization = config.get("normalization", "preserve")
    if context.reference:
        characteristic = config["rg_um"] if kind == "lognormal" else config["effective_radius_um"]
        characteristic_covered = lower < characteristic < upper
        if not characteristic_covered and not conditional_reference:
            label = "geometric mean" if kind == "lognormal" else "effective radius"
            raise ValueError(
                f"Reference PSD {label} is outside source coverage; supply a suitable psd override"
            )
        if kind == "lognormal":
            width = 4 * math.log(config["sigma_g"])
            proposed = characteristic * math.exp(-width), characteristic * math.exp(width)
        else:
            proposed = gamma_radius_bounds(characteristic, config["effective_variance"])
        bounds = [max(lower, proposed[0]), min(upper, proposed[1])]
        if bounds[0] >= bounds[1]:
            raise ValueError(
                "Reference PSD numerical radius range has no overlap with common source coverage"
            )
        normalization = "renormalize"
    constructor = lognormal_psd if kind == "lognormal" else gamma_psd
    psd = constructor(
        **{name: config[name] for name in fields[kind]},
        number_concentration_cm3=config.get("number_concentration_cm3", concentration),
        radius_range_um=bounds,
        bins=config.get("bins", 400),
        normalization=normalization,
    )
    if context.reference:
        psd = SizeDistribution(
            psd.size_um,
            psd.dndr_cm3,
            metadata={
                **psd.metadata,
                "parent_characteristic_within_source_coverage": characteristic_covered,
                "interpretation": config.get(
                    "interpretation",
                    "Reference PSD conditional on common spectral coverage; not measured climatology",
                ),
            },
            source=psd.source,
        )
    return psd
