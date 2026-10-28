"""Product writing through registered type handlers."""

from zju_scatt_interface.access.registration import registration_required
from zju_scatt_interface.extensions.operations import dispatch


@registration_required
def write(product, path, *, wavelength_um=None, wavelengths_um=None, format=None, **options):
    """Write with a registered handler; bare optics require explicit wavelengths."""
    return dispatch(
        "write",
        product,
        path,
        wavelength_um=wavelength_um,
        wavelengths_um=wavelengths_um,
        format=format,
        **options,
    )
