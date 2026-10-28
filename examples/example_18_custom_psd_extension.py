"""Register a named PSD factory and use it in a checked, offline toy calculation.

Role: Demonstrate registration and use of a custom particle size distribution.
Inputs: Built-in size bins and synthetic optical arrays; no downloaded data.
Outputs: JSON files with the evaluated configuration, PSD, bulk result and QA.
Run: python examples/example_18_custom_psd_extension.py --output-dir custom_psd_demo
Notes: Requires the ordinary installation and an existing registration. The
optical arrays are teaching data, not a physical scattering model.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import zju_scatt_interface as zsi
from zju_scatt_interface.extensions import PSDContext, PSDFactory, create_psd, register_psd
from zju_scatt_interface.psd.models import SizeDistribution


def weighted_bins(config, context):
    """Allocate the context's total concentration using explicit relative counts."""
    unknown = set(config) - {"type", "radii_um", "number_weights"}
    if unknown:
        raise ValueError(f"Unknown weighted-bin options: {sorted(unknown)}")
    radii = list(config["radii_um"])
    weights = [float(value) for value in config["number_weights"]]
    if not radii or len(radii) != len(weights):
        raise ValueError("Provide one number weight for each radius")
    if any(not math.isfinite(value) or value < 0 for value in weights):
        raise ValueError("Number weights must be finite and nonnegative")
    total_weight = math.fsum(weights)
    concentration = float(context.concentration_cm3)
    if not math.isfinite(total_weight) or total_weight <= 0:
        raise ValueError("At least one number weight must be positive")
    if not math.isfinite(concentration) or concentration <= 0:
        raise ValueError("Total concentration must be finite and positive")
    psd = SizeDistribution(
        radii,
        [concentration * value / total_weight for value in weights],
        source="tutorial_weighted_bins",
        metadata={"number_weights": weights},
    )
    if any(not context.lower_um <= radius <= context.upper_um for radius in psd.size_um):
        raise ValueError("PSD centers exceed the supplied radius context")
    return psd


def install_extension():
    """Call once per process, before consuming a configuration using this name."""
    register_psd("tutorial_weighted_bins", PSDFactory(weighted_bins))


def run_demo(output):
    install_extension()
    config = {
        "type": "tutorial_weighted_bins",
        "radii_um": [0.5, 1.0, 2.0],
        "number_weights": [1.0, 2.0, 3.0],
    }
    context = PSDContext(lower_um=0.1, upper_um=3.0, concentration_cm3=6.0)
    psd = create_psd(config, context)
    # Explicit physical units avoid ambiguity about native database conventions.
    optics = zsi.SingleParticleOptics(
        sizes=[0.5, 1.0, 2.0],
        extinction_cross_section=[1e-12, 2e-12, 4e-12],
        scattering_cross_section=[0.5e-12, 1e-12, 2e-12],
        absorption_cross_section=[0.5e-12, 1e-12, 2e-12],
        asymmetry_factor=[0.3, 0.3, 0.3],
        size_unit="um", cross_section_unit="m2",
        metadata={"source": "synthetic extension tutorial"},
    )
    bulk, remap = zsi.integrate(
        optics, psd, database_size_definition=psd.size_definition,
        truncation_policy="error",
    )
    quality = zsi.validate(bulk)
    if not quality.passed:
        raise ValueError(quality.errors)
    if not math.isclose(bulk.extinction_coefficient, 17e-6, rel_tol=1e-12):
        raise ValueError("The toy calculation differs from its analytic expectation")
    summary = {
        "interface_version": zsi.__version__, "psd_config": config,
        "context": {"lower_um": 0.1, "upper_um": 3.0, "concentration_cm3": 6.0},
        "psd": psd.to_dict(), "bulk": bulk.to_dict(),
        "remap": remap.to_dict(), "quality": quality.to_dict(),
        "interpretation": "Synthetic mechanics demonstration; not a validated scattering model or convergence study",
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Counts: {list(psd.dndr_cm3)} cm-3")
    print(f"Extinction: {bulk.extinction_coefficient:.6g} m-1")
    print(f"SSA: {bulk.single_scattering_albedo:.6g}; QA passed: {quality.passed}")
    print(f"Saved: {output}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("extension_demo/summary.json"))
    run_demo(parser.parse_args().output)
