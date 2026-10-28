"""io / applications / rttov / names domain implementation."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from zju_scatt_interface.access.registration import (
    registration_required as _registration_required,
)


@_registration_required
def rename_rttov14_species(source, destination, output_names):
    """Copy a table with configured particle names; all optical arrays stay exact.

    Keys are existing particle group names; omitted names remain unchanged.
    Names must be unique ASCII identifiers of at most 32 characters, matching
    the native RTTOV14 name field. This handles fixed tables, master lookup
    cubes and selected runtime slices. The input file is never overwritten.
    """
    from netCDF4 import Dataset, chartostring

    from zju_scatt_interface.io.applications.rttov.lookup import (
        validate_rttov14_lookup_table,
    )
    from zju_scatt_interface.io.applications.rttov.v14 import (
        _characters,
        validate_rttov14_optical_table,
    )

    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Named output must differ from the source table")
    with Dataset(source) as nc:
        if len(nc.groups) != 1 or not set(nc.groups) <= {"aertable", "hydrotable"}:
            raise ValueError("Expected one RTTOV14 aerosol or hydrometeor table")
        root = next(iter(nc.groups))
        table = nc[root]
        names = [str(n).strip() for n in chartostring(table["names"][:])]
        if set(names) != set(table.groups) or len(names) != len(set(names)):
            raise ValueError("Source names registry and particle groups disagree")
        if int(table["version"][...]) != 4 or int(table["id"][...]) != 0:
            raise ValueError("Expected a version-4 RTTOV14 user table")
        renamed = [output_names.get(name, name) for name in names]
        if any(
            not isinstance(n, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", n)
            for n in renamed
        ):
            raise ValueError("Output names must be ASCII identifiers of 1..32 characters")
        if len(set(renamed)) != len(renamed):
            raise ValueError("Output particle names must be unique")
        is_grid = "native_runtime_compatible" in nc.ncattrs()
    validator = validate_rttov14_lookup_table if is_grid else validate_rttov14_optical_table
    validator(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        shutil.copy2(source, temporary)
        with Dataset(temporary, "a") as nc:
            table = nc[root]
            # Temporary names permit swaps, e.g. DU -> BC and BC -> DU.
            staging = {old: "rename_" + uuid.uuid4().hex for old in names}
            for old, intermediate in staging.items():
                table.renameGroup(old, intermediate)
            for old, new in zip(names, renamed):
                table.renameGroup(staging[old], new)
            table["names"][:] = _characters(renamed, len(table.dimensions["str_name_dim"]))
            nc.species_name_map = json.dumps(dict(zip(names, renamed)))
            nc.naming_source = str(source.resolve())
        validation = validator(temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    validation["path"] = str(destination)
    return {
        "path": str(destination),
        "name_mapping": dict(zip(names, renamed)),
        "validation": validation,
    }
