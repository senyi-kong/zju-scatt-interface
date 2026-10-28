"""A separately imported extension module exercising real existing workflows.

Executed in a fresh interpreter so its registrations never affect other tests.
The synthetic particle reuses water-sphere optics; it asserts extension mechanics,
not the validity of a new scientific particle model.
"""

import hashlib
import json
import math
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import zju_scatt_interface as scatt
from tests.test_bulk_pipeline import create_source
from zju_scatt_interface.bulk.tables import _make_psd
from zju_scatt_interface.cli.main import main
from zju_scatt_interface.cli.parser import build_parser
from zju_scatt_interface.config.particles import get_particle_profile, validate_profile_parameters
from zju_scatt_interface.config.reference import scheme_reference
from zju_scatt_interface.config.scheme import ParticleComponent, Scheme
from zju_scatt_interface.extensions import (
    Command,
    Exporter,
    NativeModel,
    ParticleDefinition,
    PSDFactory,
    export,
    register_command,
    register_exporter,
    register_native_model,
    register_operation,
    register_particle,
    register_plotter,
    register_psd,
    register_serializer,
    validate_export,
    ExtensionError,
)
from zju_scatt_interface.extensions.particles import get_particle_definition
from zju_scatt_interface.io.native import (
    native_template_from_reference,
    read_native_optical_arrays,
    write_native_optical_output,
)
from zju_scatt_interface.psd.models import SizeDistribution
from zju_scatt_interface.sources.adapters.registry import get_particle_adapter
from zju_scatt_interface.sources.adapters.spheres import WaterCloudWavelengthAdapter


class ProbeAdapter(WaterCloudWavelengthAdapter):
    particle_type = "extension_probe_sphere"


def plan_particle(scheme, component):
    profile = get_particle_profile(component.particle_type)
    return {"wavelength_um": list(scheme.wavelengths_um)}, {
        "sources": [f"Single_opt/{profile.database_directory}/"],
        "particle_types": [profile.particle_type],
        "target_wavelengths": list(scheme.wavelengths_um),
        "target_wavelength_mode": "interp",
        "quiet": True,
        "download": False,
    }


def particle_inputs(component):
    if component.refractive_index != {"mode": "database"}:
        raise ValueError("Probe particle requires database optical constants")
    return {}, None


def make_probe_psd(config, context):
    if set(config) - {"type", "counts"}:
        raise ValueError("Unknown probe PSD option")
    return SizeDistribution([0.5, 1.0, 2.0], config["counts"])


@dataclass
class ProbeProduct:
    value: float


def write_product(product, path, **options):
    path = Path(path)
    path.write_text(json.dumps({"value": product.value}), encoding="utf-8")
    return path


def write_export(data, path, **options):
    return write_product(ProbeProduct(data.extinction_coefficient), path)


def validate_probe(arrays, template):
    if set(arrays) != {"coefficient"} or arrays["coefficient"].shape != (2,):
        raise ValueError("Probe template requires two coefficients")
    if (arrays["coefficient"] < 0).any():
        raise ValueError("Negative coefficient")


def serialize_probe(path, arrays, template):
    Path(path).write_text(json.dumps(arrays["coefficient"].tolist()), encoding="utf-8")


def template_probe(path):
    return {
        "schema_version": 1,
        "model": "probe_native",
        "format": "probe_json",
        "variables": {"coefficient": {"source": "coefficient", "shape": [2]}},
    }


def configure_command(parser):
    parser.add_argument("--count", type=int, default=2)


def validate_command(args):
    if args.count < 1:
        raise ValueError("count must be positive")


def run_command(args, client):
    return args.count


def install():
    profile = replace(
        get_particle_definition("sphere_water_cloud").profile,
        particle_type=ProbeAdapter.particle_type,
        aliases=("probe sphere",),
        database_directory=ProbeAdapter.particle_type,
        display_name="Synthetic extension probe",
    )
    register_particle(
        ParticleDefinition(profile, ProbeAdapter, ("wavelength",), plan_particle, particle_inputs)
    )
    register_psd("probe_bins", PSDFactory(make_probe_psd), aliases=("probe_counts",))
    register_operation("write", ProbeProduct, write_product)
    register_operation("validate", ProbeProduct, lambda product, **options: product.value >= 0)
    register_operation("plot", ProbeProduct, lambda product, **options: [product.value])
    register_operation(
        "build", ProbeProduct, lambda product, **options: ProbeProduct(product.value * 2)
    )
    register_operation("plan", ProbeProduct, lambda product, **options: {"value": product.value})
    register_plotter("probe", lambda product, **options: [product.value])
    register_exporter(
        "probe_export",
        Exporter(
            write_export, lambda path, **options: json.loads(Path(path).read_text())["value"] >= 0
        ),
    )
    register_native_model(
        "probe_native",
        NativeModel(
            validate_probe,
            read=lambda path: {"coefficient": json.loads(Path(path).read_text())},
            template=template_probe,
        ),
    )
    register_serializer("probe_json", serialize_probe)
    register_command(
        Command(
            "probe", "Extension acceptance probe", configure_command, run_command, validate_command
        )
    )


def fingerprints():
    root = Path(scatt.__file__).parent
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*.py")
    }


def run_probe(output):
    before = fingerprints()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="probe_", dir=output))
    install()
    for invalid_registration in (
        lambda: register_psd("gamma", PSDFactory(make_probe_psd)),
        lambda: register_command(Command("bulk-opt", "collision", configure_command, run_command)),
        lambda: register_operation("write", ProbeProduct, write_product),
        lambda: register_native_model("custom", NativeModel(validate_probe)),
        lambda: register_serializer("hdf5", serialize_probe),
        lambda: register_exporter("rttov14", Exporter(write_export)),
        lambda: register_particle(
            replace(
                get_particle_definition("probe sphere"),
                profile=replace(
                    get_particle_profile("probe sphere"),
                    particle_type="collision",
                    aliases=("water_cloud",),
                ),
            )
        ),
    ):
        try:
            invalid_registration()
        except ExtensionError:
            pass
        else:
            raise AssertionError("A conflicting extension registration was accepted")
    assert get_particle_profile("probe sphere").particle_type == ProbeAdapter.particle_type
    assert isinstance(get_particle_adapter("probe sphere"), ProbeAdapter)
    assert validate_profile_parameters("probe sphere", {"wavelength": 0.6})
    assert (
        scheme_reference("probe sphere")["particle_profiles"][0]["typed_component"]
        == "ParticleComponent"
    )

    psd = _make_psd({"type": "probe_counts", "counts": [1.0, 2.0, 1.0]}, {}, 0.1, 10.0, 4, "error")
    assert psd.number_concentration_cm3 == 4
    component = ParticleComponent("probe", ProbeAdapter.particle_type, psd, {"mode": "database"})
    scheme = Scheme("extension_probe", (0.5, 0.6), (component,))
    queries = scatt.validate(scheme)
    assert queries[0].particle_type == ProbeAdapter.particle_type
    paths = [
        work / f"L1_{ProbeAdapter.particle_type}_wl_{w:.3f}_um_ref_1.3_0.nc" for w in (0.5, 0.7)
    ]
    for path, wavelength in zip(paths, (0.5, 0.7)):
        create_source(path, wavelength=wavelength, phase=True)
    dataset = scatt.build(
        scheme,
        source_paths=paths,
        workspace=work / "workspace",
        include_phase_matrix=True,
        check_convergence=False,
    )
    result = dataset.components["probe"][1].bulk
    assert result.number_concentration == 4 and math.isfinite(result.extinction_coefficient)
    assert scatt.validate(result).passed
    baseline_paths = [
        work / f"L1_sphere_water_cloud_wl_{w:.3f}_um_ref_1.3_0.nc" for w in (0.5, 0.7)
    ]
    for path, wavelength in zip(baseline_paths, (0.5, 0.7)):
        create_source(path, wavelength=wavelength, phase=True)
    baseline = scatt.compute_population(
        "sphere_water_cloud",
        baseline_paths,
        psd,
        wavelength=0.6,
        include_phase_matrix=True,
        check_convergence=False,
    ).bulk
    for field in (
        "extinction_coefficient",
        "scattering_coefficient",
        "absorption_coefficient",
        "single_scattering_albedo",
        "asymmetry_factor",
        "number_concentration",
    ):
        assert math.isclose(getattr(result, field), getattr(baseline, field), rel_tol=1e-12)
    canonical = scatt.write(dataset, work / "probe.h5")
    assert scatt.validate(canonical).passed
    exported = export("probe_export", result, work / "export.json")
    assert validate_export("probe_export", exported)
    product = ProbeProduct(3)
    assert scatt.build(product).value == 6 and scatt.plan(product) == {"value": 3}
    assert scatt.validate(product) and scatt.plot(product) == [3]
    assert scatt.plot(product, kind="probe") == [3]
    assert json.loads(scatt.write(product, work / "product.json").read_text())["value"] == 3
    native = write_native_optical_output(
        work / "native.json", {"coefficient": [1.0, 2.0]}, template_probe(None)
    )
    assert read_native_optical_arrays(native, model="probe_native")["coefficient"] == [1.0, 2.0]
    assert native_template_from_reference(native, model="probe_native")["format"] == "probe_json"
    failed = work / "invalid.json"
    try:
        write_native_optical_output(failed, {"coefficient": [-1.0, 2.0]}, template_probe(None))
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid extension output was accepted")
    assert not failed.exists()
    assert build_parser().parse_args(["probe", "--count", "7"]).extension_command
    assert main(["probe", "--count", "7"]) == 7
    assert main(["probe", "--count", "0"]) == 2
    assert before == fingerprints(), "Extension registration modified existing source files"
    (work / "acceptance.json").write_text(
        json.dumps(
            {
                "passed": True,
                "source_files_unchanged": len(before),
                "particle": ProbeAdapter.particle_type,
            }
        ),
        encoding="utf-8",
    )
    print(f"Extension acceptance passed: {work}")
