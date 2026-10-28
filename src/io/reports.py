"""io / reports domain implementation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)
from zju_scatt_interface.access.workflow import _write_json
from zju_scatt_interface.io.canonical import (
    _write_population as write_bulk_calculation_netcdf,
)
from zju_scatt_interface.io.canonical import validate_file


def _scalar_columns(bulk):
    """Optical values at the member's reference population, without shape scaling."""
    if (
        bulk.metadata.get("bulk_coefficient_unit") != "m-1"
        or bulk.metadata.get("number_concentration_output_unit") != "cm-3"
    ):
        raise ValueError(
            "Standard bulk CSV output requires m^-1 coefficients and cm^-3 concentration"
        )
    values = {
        f"{name}_coefficient_{unit}": float(getattr(bulk, f"{name}_coefficient")) * factor
        for unit, factor in (("m-1", 1.0), ("Mm-1", 1e6))
        for name in ("extinction", "scattering", "absorption")
    }
    values.update(
        single_scattering_albedo=float(bulk.single_scattering_albedo),
        asymmetry_factor=float(bulk.asymmetry_factor),
        **{"number_concentration_cm-3": float(bulk.number_concentration)},
    )
    return values


def _member_rows(calculation):
    rows = [
        {
            "population": f"member_{index}",
            "ensemble_member": index,
            "number_fraction": member.weight,
            "parameters_json": json.dumps(member.parameters, sort_keys=True),
            "allocated_number_concentration_cm-3": member.weight * member.bulk.number_concentration,
            **_scalar_columns(member.bulk),
        }
        for index, member in enumerate(calculation.members)
    ]
    rows.append(
        {
            "population": "ensemble_average",
            "ensemble_member": "",
            "number_fraction": 1.0,
            "parameters_json": "{}",
            "allocated_number_concentration_cm-3": calculation.bulk.number_concentration,
            **_scalar_columns(calculation.bulk),
        }
    )
    return rows


@_registration_required
def save_bulk_calculation(
    calculation,
    directory,
    *,
    component_name="bulk_optics",
    source_manifest=None,
    size_distribution=None,
    netcdf_path="bulk_optics.nc",
    title=None,
    include_members=False,
    l2_lognormal=False,
):
    if not isinstance(include_members, bool) or not isinstance(l2_lognormal, bool):
        raise ValueError("include_members and l2_lognormal must be booleans")
    if l2_lognormal:
        from zju_scatt_interface.io.l2 import (
            _lognormal_member_specs,
            write_l2_lognormal_members,
        )

        _lognormal_member_specs(calculation, size_distribution)  # Validate before writing outputs.
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    bulk = calculation.bulk
    scalars = _scalar_columns(bulk)
    rows = _member_rows(calculation) if include_members else [scalars]
    outputs = {}
    path = Path(netcdf_path)
    path = path if path.is_absolute() else root / path
    kwargs = {"component_name": component_name, "source_manifest": source_manifest}
    if title is not None:
        kwargs["title"] = title
    target = write_bulk_calculation_netcdf(path, calculation, **kwargs, format="netcdf4")
    validate_file(target).require_valid()
    outputs["nc"] = str(target)
    path = root / "bulk_optics.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    outputs["scalars_csv"] = str(path)
    if bulk.phase_matrix is not None:
        angles = bulk.metadata.get("scattering_angles_degrees", ())
        if len(angles) != len(bulk.phase_matrix):
            raise ValueError("Bulk phase matrix and scattering-angle lengths differ")
        path = root / "bulk_phase_matrix.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["angle_degrees", "P11", "P12", "P22", "P33", "P43", "P44"])
            for angle, matrix in zip(angles, bulk.phase_matrix):
                writer.writerow(
                    [
                        angle,
                        matrix[0][0],
                        matrix[0][1],
                        matrix[1][1],
                        matrix[2][2],
                        matrix[3][2],
                        matrix[3][3],
                    ]
                )
        outputs["phase_csv"] = str(path)
    if size_distribution is not None:
        outputs["psd_csv"] = str(size_distribution.to_csv(root / "size_distribution.csv"))
    if l2_lognormal:
        outputs["l2_members"] = [
            str(path) for path in write_l2_lognormal_members(root, calculation, size_distribution)
        ]
    outputs["report"] = str(root / "summary.json")
    _write_json(
        outputs["report"],
        {
            "calculation": calculation.to_dict(),
            "bulk_optics": scalars,
            "member_scalar_rows": rows[:-1] if include_members else [],
            "member_optics_interpretation": "Member optical coefficients describe pure populations at their reference concentration; number_fraction is applied only when combining integrated bulk results. allocated_number_concentration_cm-3 records each shape's share of the total population.",
            "size_distribution": None if size_distribution is None else size_distribution.to_dict(),
            "outputs": outputs,
        },
    )
    return outputs
