"""Declarative built-in native model and backend bindings."""

from functools import partial

from zju_scatt_interface.extensions.native import NativeModel
from zju_scatt_interface.io.applications.arts import native as arts
from zju_scatt_interface.io.applications.common import scalar_phase_projection
from zju_scatt_interface.io.applications.crtm import native as crtm
from zju_scatt_interface.io.applications.rttov import native as rttov
from zju_scatt_interface.io.serializers import serialize_hdf5, serialize_netcdf


def _custom_validate(arrays, template):
    """Custom arrays already passed the portable template validation."""


def _phase_only(arrays, template):
    raise ValueError(
        "unknown native model for template output; this binding supports phase projection only"
    )


def install(models, serializers):
    models.register("custom", NativeModel(_custom_validate))
    models.register(
        "arts2",
        NativeModel(
            arts.validate_arrays,
            arts.read_arrays,
            arts.reference_template,
            arts.bulk_fields,
        ),
    )
    models.register(
        "crtm-cloud-v3",
        NativeModel(
            crtm._validate_crtm,
            crtm.read_arrays,
            crtm.reference_template,
            crtm.bulk_fields,
            partial(scalar_phase_projection, convention="crtm_streams"),
        ),
    )
    models.register(
        "rttov13",
        NativeModel(
            rttov._validate_rttov,
            rttov.read_arrays,
            rttov.reference_template,
            rttov.bulk_fields,
            partial(scalar_phase_projection, convention="legendre"),
            rttov.encode_attribute,
        ),
    )
    models.register(
        "rttov14",
        NativeModel(
            _phase_only,
            phase=partial(scalar_phase_projection, convention="legendre"),
        ),
    )
    serializers.register("arts-xml", arts.serialize_xml)
    serializers.register("hdf5", serialize_hdf5)
    serializers.register("netcdf3", serialize_netcdf)
    serializers.register("netcdf4", serialize_netcdf)
    serializers.register("crtm-binary", crtm._write_crtm_binary)
