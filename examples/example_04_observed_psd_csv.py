"""Load an observed PSD unchanged and write a validated scheme configuration.

Role:
    Production example

Inputs:
    Synthetic measurement-format bin counts.

Outputs:
    PSD CSV, validated scheme inputs and reports; counts are not normalized.

Run:
    From the package root: python examples/example_04_observed_psd_csv.py --help

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.

Original example details:
    Load an observed PSD unchanged and write a validated scheme configuration.

    The CSV values are discrete represented-bin concentrations in cm-3.
    Writing the scheme standardizes configuration syntax; it does not normalize PSD counts.

    Run:

        python examples/example_04_observed_psd_csv.py         --output-dir observed_psd_example_output
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from zju_scatt_interface.config.scheme import Scheme, SchemeOutput, SulfateComponent
from zju_scatt_interface.psd.models import SizeDistribution


def run_example(output_dir: Path) -> dict[str, object]:
    """Convert a CSV PSD into a scheme and save a diagnostic plot/report."""

    # Keep all generated files together so the example can be rerun without
    # overwriting source data in ``examples/data``.
    output_dir.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent / "data" / "observed_psd_example.csv"

    # The CSV stores one concentration value per represented radius bin.  The
    # explicit size definition prevents an ambiguous radius convention from
    # entering later bulk-optics calculations.
    distribution = SizeDistribution.from_delimited(
        source,
        size_column="radius_um",
        dndr_column="dndr_cm3",
        size_unit="um",
        size_definition="volume_equivalent_sphere_radius",
    )
    component = SulfateComponent(
        "observed_sulfate",
        relative_humidity=0.8,
        size_distribution=distribution,
    )
    scheme = Scheme(
        "observed_psd_sulfate",
        (0.44, 0.55, 0.67, 0.87),
        (component,),
        truncation_policy="truncate",
        output_settings=SchemeOutput("observed_psd_sulfate.nc", "netcdf4"),
    )

    # Validation resolves the component's data dependencies and provides a
    # compact count for the machine-readable report.
    queries = scheme.validate()
    normalized = scheme.write_json(output_dir / "observed_psd_scheme.json")

    # Use a headless Matplotlib backend so this example also works on WSL and
    # in continuous-integration environments without a desktop display.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(7.5, 5.0), constrained_layout=True)
    axis.loglog(
        distribution.size_um,
        distribution.dndr_cm3,
        "o-",
        color="#4C72B0",
    )
    axis.set(
        xlabel="Volume-equivalent sphere radius (um)",
        ylabel="Concentration per represented bin (cm-3)",
        title="Observed PSD loaded from CSV",
    )
    axis.grid(True, which="both", alpha=0.25)
    figure_path = output_dir / "observed_psd.png"
    figure.savefig(figure_path, dpi=180)
    plt.close(figure)
    report = {
        "status": "passed",
        "source": str(source),
        "point_count": len(distribution.size_um),
        "number_concentration_cm3": distribution.number_concentration_cm3,
        "size_definition": distribution.size_definition,
        "dependency_query_count": len(queries),
        "normalized_scheme": str(normalized),
        "figure": str(figure_path),
    }
    (output_dir / "observed_psd_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the output directory and run the CSV workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("observed_psd_example_output"),
    )
    args = parser.parse_args(argv)
    print(json.dumps(run_example(args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
