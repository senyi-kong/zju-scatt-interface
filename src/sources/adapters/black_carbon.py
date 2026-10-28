"""Native-index and wavelength black-carbon adapters."""

from __future__ import annotations

import math
import re

import zju_scatt_interface.access.metadata as _domain_access_metadata
from zju_scatt_interface.optics.refractive_index import (
    resolve_grid_refractive_indices,
)
from zju_scatt_interface.sources.adapters.base import ParticleAdapter
from zju_scatt_interface.sources.adapters.boundaries import (
    AdapterError,
    database_type,
    refractive_index_scheme,
)


class BlackCarbonGridAdapter(ParticleAdapter):
    particle_type = "encapsulated_fractal_aggregates_black_carbon"
    axes = (
        "black_carbon_refractive_index_real",
        "black_carbon_refractive_index_imaginary",
        "hygroscopic_refractive_index_real",
        "hygroscopic_refractive_index_imaginary",
        "df",
        "vf",
    )
    internal_axis = "vf"

    def resolve(self, source_paths, **kwargs):
        from zju_scatt_interface.sources.adapters.base import (
            _expand_netcdf_paths,
            _normalized_parameters,
        )

        parameters = dict(kwargs.pop("parameters", None) or {})
        kind = parameters.pop("database_type", None)
        scheme = parameters.pop("ri_scheme", None)
        if kind is None:
            has_indices = any(
                "refractive_index" in name for name in _normalized_parameters(parameters)
            ) or bool(kwargs.get("refractive_index_tables"))
            kind = (
                "wavelength"
                if not has_indices
                and any(
                    database_type(p) == "wavelength" for p in _expand_netcdf_paths(source_paths)
                )
                else "refractive_index_grid"
            )
        if kind not in {"refractive_index_grid", "wavelength"}:
            raise AdapterError("database_type must be refractive_index_grid or wavelength")
        if scheme is not None and scheme not in {"v1.2.1", "v1.2.2"}:
            raise AdapterError("ri_scheme must be v1.2.1 or v1.2.2")
        paths = [p for p in _expand_netcdf_paths(source_paths) if database_type(p) == kind]
        if kind == "wavelength":
            scheme = scheme or "v1.2.1"
            paths = [p for p in paths if refractive_index_scheme(p) == scheme]
            adapter = BlackCarbonWavelengthAdapter()
        else:
            if scheme is not None and "refractive_index_tables" not in kwargs:
                from zju_scatt_interface.optics.refractive_index import (
                    default_refractive_index_paths,
                )

                kwargs["refractive_index_tables"] = default_refractive_index_paths(
                    self.particle_type, ri_scheme=scheme
                )
            adapter = None
        if not paths:
            raise AdapterError(
                f"No black-carbon sources for database_type={kind}, ri_scheme={scheme}"
            )
        resolution = (
            adapter.resolve(paths, parameters=parameters, **kwargs)
            if adapter
            else super().resolve(paths, parameters=parameters, **kwargs)
        )
        resolution.provenance.database_type = kind
        resolution.provenance.ri_scheme = scheme
        return resolution

    def _target(self, wavelength_um, parameters, tables):
        from zju_scatt_interface.sources.adapters.base import (
            _finite,
        )

        unknown = set(parameters) - set(self.axes)
        if unknown:
            raise AdapterError("Unsupported black-carbon parameters: " + ", ".join(sorted(unknown)))
        for name in ("df", "vf"):
            if name not in parameters:
                raise AdapterError(f"Black carbon requires {name}.")
        resolved = resolve_grid_refractive_indices(
            self.particle_type,
            [wavelength_um],
            parameters=parameters,
            tables=tables,
        )[0]
        target = {
            **{name: float(value) for name, value in resolved.values.items()},
            "df": _finite(parameters["df"], "df"),
            "vf": _finite(parameters["vf"], "vf"),
        }
        # Coverage belongs to this database, not the union of both BC releases.
        # Bracketing below checks the actual selected files, including IR indices.
        if any(not math.isfinite(float(value)) for value in target.values()):
            raise AdapterError("Black-carbon coordinates must be finite")
        return target, resolved.input_mode, dict(resolved.sources), []

    def _file_coordinates(self, path):
        from zju_scatt_interface.sources.adapters.base import (
            _match_number,
        )

        text = path.name
        pattern = _domain_access_metadata.NUMBER_PATTERN
        match = re.search(
            rf"ref_bc_({pattern})_({pattern})_hygro_({pattern})_({pattern})",
            text,
            re.IGNORECASE,
        )
        if not match:
            raise AdapterError("not a black-carbon L1 filename")
        return {
            "black_carbon_refractive_index_real": float(match.group(1)),
            "black_carbon_refractive_index_imaginary": float(match.group(2)),
            "hygroscopic_refractive_index_real": float(match.group(3)),
            "hygroscopic_refractive_index_imaginary": float(match.group(4)),
            "df": _match_number(text, rf"(?:^|_)df_({pattern})(?=_)", "df"),
        }

    def _expand_internal(self, records):
        from zju_scatt_interface.sources.adapters.base import (
            _FileRecord,
            _read_coordinate,
        )

        result = []
        for record in records:
            for index, vf in enumerate(_read_coordinate(record.path, "vf")):
                result.append(
                    _FileRecord(
                        record.path,
                        {**record.coordinates, "vf": vf},
                        {"Df": 0, "vf": index},
                    )
                )
        return result, ["vf read from the file coordinate and mapped to coordinate_indices"]


class BlackCarbonWavelengthAdapter(ParticleAdapter):
    particle_type = BlackCarbonGridAdapter.particle_type
    axes = ("wavelength", "df", "vf")
    internal_axis = "vf"
    _expand_internal = BlackCarbonGridAdapter._expand_internal

    def _target(self, wavelength_um, parameters, tables):
        from zju_scatt_interface.sources.adapters.base import _finite

        if tables or any("refractive_index" in name for name in parameters):
            raise AdapterError("The wavelength BC database uses its selected built-in RI scheme")
        if set(parameters) - {"df", "vf"}:
            raise AdapterError("Wavelength BC accepts df and vf only")
        if not {"df", "vf"} <= set(parameters):
            raise AdapterError("Black carbon requires df and vf")
        return (
            {
                "wavelength": wavelength_um,
                "df": _finite(parameters["df"], "df"),
                "vf": _finite(parameters["vf"], "vf"),
            },
            "database",
            {},
            [],
        )

    def _file_coordinates(self, path):
        from zju_scatt_interface.sources.adapters.base import _match_number

        metadata = _domain_access_metadata.extract_scatt_metadata(path.name)
        return {
            "wavelength": metadata["wavelength_um"],
            "df": _match_number(
                path.name, rf"_df_({_domain_access_metadata.NUMBER_PATTERN})_", "df"
            ),
        }


def interpolation_policy(values, nodes):
    from zju_scatt_interface.optics.interpolation import InterpolationError
    from zju_scatt_interface.sources.adapters.boundaries import (
        database_type,
        refractive_index_scheme,
    )

    identified = [node for node in nodes if "_ref_bc_" in node.source]
    kinds = {database_type(node.source) for node in identified}
    schemes = {refractive_index_scheme(node.source) for node in identified}
    schemes.discard(None)
    if len(kinds) > 1 or len(schemes) > 1:
        raise InterpolationError("BC interpolation must use one database type and one RI scheme")
    expected = ("wavelength", "df", "vf") if "wavelength" in values else BlackCarbonGridAdapter.axes
    return expected, False
