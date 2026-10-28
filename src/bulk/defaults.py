"""Reference populations supplied by a registered particle implementation."""

from zju_scatt_interface.access.registration import registration_required
from zju_scatt_interface.extensions.particles import get_particle_definition


@registration_required
def default_bulk_assumptions(particle_type, source_paths=None, *, preset="literature_v1"):
    definition = get_particle_definition(particle_type)
    if definition.defaults is None:
        raise ValueError(
            f"No reference population is declared for {particle_type!r}; supply an explicit PSD"
        )
    return definition.defaults(source_paths, preset=preset)
