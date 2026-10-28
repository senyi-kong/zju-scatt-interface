"""Release-level vertical-slice coverage for every supported particle profile."""

import math
import tempfile
import unittest
from pathlib import Path

from zju_scatt_interface.bulk.models import BulkDataset
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.config.particles import list_particle_profiles, validate_profile_parameters
from zju_scatt_interface.io.canonical import _write_dataset as _write_dataset
from zju_scatt_interface.io.canonical import read, validate_file
from zju_scatt_interface.optics.interpolation import OpticalNode, interpolate_nodes
from zju_scatt_interface.optics.models import SingleParticleOptics
from zju_scatt_interface.optics.refractive_index import wavelength_to_um
from zju_scatt_interface.psd.models import SizeDistribution


def create_fixture(
    path: Path,
    *,
    wavelength: float | None,
    multiplier: float,
    rh: tuple[float, ...] | None = None,
    vf: tuple[float, ...] | None = None,
) -> None:
    import numpy as np
    from netCDF4 import Dataset

    path.parent.mkdir(parents=True, exist_ok=True)
    radii = np.geomspace(0.1, 5.0, 20)
    with Dataset(path, "w") as dataset:
        dataset.createDimension("xsize_veq", len(radii))
        if wavelength is None:
            xsize = np.geomspace(0.5, 20.0, len(radii))
        else:
            dataset.createVariable("wavelength", "f8")[:] = wavelength
            xsize = 2 * math.pi * radii / wavelength
        dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = xsize

        dimensions: list[str] = []
        if "black_carbon" in path.name:
            dataset.createDimension("Df", 1)
            dataset.createVariable("Df", "f8", ("Df",))[:] = [2.0]
            dimensions.append("Df")
        if vf is not None:
            dataset.createDimension("vf", len(vf))
            dataset.createVariable("vf", "f8", ("vf",))[:] = vf
            dimensions.append("vf")
        if rh is not None:
            dataset.createDimension("rh", len(rh))
            dataset.createVariable("rh", "f8", ("rh",))[:] = rh
            dimensions.append("rh")
        dimensions.append("xsize_veq")

        shape = tuple(dataset.dimensions[name].size for name in dimensions)
        base = multiplier * np.geomspace(0.25, 80.0, len(radii))
        cext = np.empty(shape, dtype=float)
        cext[...] = base
        if vf is not None:
            for index in range(len(vf)):
                cext[:, index, :] *= 1.0 + 0.25 * index
        if rh is not None:
            for index in range(len(rh)):
                cext[index, :] *= 1.0 + 0.2 * index
        dataset.createVariable("cext", "f8", tuple(dimensions))[:] = cext
        dataset.createVariable("ssa", "f8", tuple(dimensions))[:] = 0.72
        dataset.createVariable("g", "f8", tuple(dimensions))[:] = 0.45


def create_all_profile_fixtures(root: Path) -> dict[str, Path]:
    roots = {
        profile.particle_type: root / profile.particle_type
        for profile in list_particle_profiles()
    }
    for particle_type in (
        "sphere_sulfate",
        "sphere_nitrate",
        "sphere_organic_carbon",
    ):
        for wavelength, multiplier in ((0.5, 1.0), (0.7, 1.4)):
            create_fixture(
                roots[particle_type]
                / (
                    f"L1_{particle_type}_wl_{wavelength:.3f}_um_"
                    "ref_1.500e+00_1.000e-08.nc"
                ),
                wavelength=wavelength,
                multiplier=multiplier,
                rh=(0.0, 50.0),
            )
    for wavelength, multiplier in ((0.5, 1.0), (0.7, 1.4)):
        create_fixture(
            roots["sphere_water_cloud"]
            / (
                f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_"
                "ref_1.330e+00_1.000e-08.nc"
            ),
            wavelength=wavelength,
            multiplier=multiplier,
        )
        create_fixture(
            roots["coated_super_spheroid_seasalt"]
            / (
                "L1_coated_super_spheroid_seasalt_multiparas_"
                f"wl_{wavelength:.3f}_um_ref_1.490e+00_2.000e-07.nc"
            ),
            wavelength=wavelength,
            multiplier=multiplier,
            rh=(-50.0, 50.0),
        )
        create_fixture(
            roots["super_spheroid_ice"]
            / (
                "L1_super_spheroid_ice_n_2.000_asp_1.000_"
                f"wl_{wavelength:.3f}_um_ref_1.310e+00_1.000e-08_t_220k.nc"
            ),
            wavelength=wavelength,
            multiplier=multiplier,
        )
    for roundness, multiplier in ((2.0, 1.0), (2.5, 1.5)):
        create_fixture(
            roots["super_spheroid"]
            / (
                f"L1_super_spheroid_n_{roundness:.3f}_asp_1.000_wl_nan_"
                "ref_1.500e+00_1.000e-02.nc"
            ),
            wavelength=None,
            multiplier=multiplier,
        )
    create_fixture(
        roots["encapsulated_fractal_aggregates_black_carbon"]
        / (
            "L1_encapsulated_fractal_aggregates_black_carbon_df_2.00_wl_nan_"
            "ref_bc_1.650e+00_5.500e-01_hygro_1.300e+00_1.000e-02.nc"
        ),
        wavelength=None,
        multiplier=1.2,
        vf=(0.2, 0.4),
    )
    return roots


PROFILE_REQUESTS = {
    "encapsulated_fractal_aggregates_black_carbon": {
        "bc_mr": 1.65,
        "bc_mi": 0.55,
        "hygro_mr": 1.3,
        "hygro_mi": 0.01,
        "df": 2.0,
        "vf": 0.3,
    },
    "super_spheroid": {
        "mr": 1.5,
        "mi": 0.01,
        "roundness": 2.25,
        "aspect_ratio": 1.0,
    },
    "coated_super_spheroid_seasalt": {
        "relative_humidity": 0.5,
        "humidity_branch": "deliquescence",
    },
    "super_spheroid_ice": {
        "temperature": 220.0,
        "roundness": 2.0,
        "aspect_ratio": 1.0,
    },
    "sphere_sulfate": {"relative_humidity": 0.25},
    "sphere_nitrate": {"relative_humidity": 0.25},
    "sphere_organic_carbon": {"relative_humidity": 0.25},
    "sphere_water_cloud": {},
}

EXACT_PROFILE_REQUESTS = {
    **PROFILE_REQUESTS,
    "encapsulated_fractal_aggregates_black_carbon": {
        **PROFILE_REQUESTS[
            "encapsulated_fractal_aggregates_black_carbon"
        ],
        "vf": 0.2,
    },
    "super_spheroid": {
        **PROFILE_REQUESTS["super_spheroid"],
        "roundness": 2.0,
    },
    "sphere_sulfate": {"relative_humidity": 0.0},
    "sphere_nitrate": {"relative_humidity": 0.0},
    "sphere_organic_carbon": {"relative_humidity": 0.0},
}


class Phase11CoordinateMatrixTests(unittest.TestCase):
    def test_wavelength_units_are_equivalent_across_every_profile(self):
        for profile in list_particle_profiles():
            with self.subTest(profile=profile.particle_type):
                self.assertAlmostEqual(wavelength_to_um(550, "nm"), 0.55)
                self.assertAlmostEqual(wavelength_to_um(0.55, "um"), 0.55)
                self.assertAlmostEqual(
                    wavelength_to_um(10000 / 0.55, "cm-1"), 0.55
                )

    def test_every_profile_accepts_canonical_mid_domain_coordinates(self):
        for profile in list_particle_profiles():
            supplied: dict[str, object] = {}
            for parameter in profile.parameters:
                if parameter.role.value == "derived":
                    continue
                if parameter.name == "wavelength":
                    lower = parameter.minimum or 0.5
                    upper = parameter.maximum or 0.7
                    supplied[parameter.name] = (lower + upper) / 2
                elif parameter.choices:
                    supplied[parameter.name] = parameter.choices[0]
                elif parameter.role.value == "required":
                    if parameter.grid_values:
                        supplied[parameter.name] = parameter.grid_values[0]
                    elif (
                        parameter.minimum is not None
                        and parameter.maximum is not None
                    ):
                        supplied[parameter.name] = (
                            parameter.minimum + parameter.maximum
                        ) / 2
            if profile.data_structure.value == "grid_based":
                supplied.update(PROFILE_REQUESTS[profile.particle_type])
            with self.subTest(profile=profile.particle_type):
                normalized = validate_profile_parameters(
                    profile.particle_type, supplied
                )
                self.assertIn("wavelength", normalized)

    def test_radius_contract_is_explicit_for_every_profile(self):
        for profile in list_particle_profiles():
            with self.subTest(profile=profile.particle_type):
                self.assertIn(
                    profile.default_size_definition,
                    profile.supported_size_definitions,
                )
                self.assertEqual(
                    profile.default_size_definition,
                    "volume_equivalent_sphere_radius",
                )
                if "maximum_dimension_radius" in profile.supported_size_definitions:
                    self.assertIn("xsize_maxd", profile.native_size_variables)

    def test_original_super_spheroid_symbols_map_to_correct_coordinates(self):
        optics = SingleParticleOptics(
            sizes=[1.0],
            extinction_cross_section=[1.0],
            scattering_cross_section=[0.8],
            absorption_cross_section=[0.2],
            asymmetry_factor=[0.5],
            size_unit="um",
            cross_section_unit="m2",
        )
        product = interpolate_nodes(
            "super_spheroid",
            [
                OpticalNode(
                    {
                        "mr": 1.5,
                        "mi": 0.01,
                        "n": 2.0,
                        "alpha": 1.25,
                    },
                    optics,
                    "alias_node",
                )
            ],
            {
                "refractive_index_real": 1.5,
                "refractive_index_imaginary": 0.01,
                "roundness": 2.0,
                "aspect_ratio": 1.25,
            },
        )
        self.assertEqual(product.provenance.method, "exact")


class Phase11AllProfileVerticalSliceTests(unittest.TestCase):
    def setUp(self):
        try:
            import h5py  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("netCDF4 and h5py are required")

    def test_every_profile_interpolates_integrates_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = create_all_profile_fixtures(root / "l1")
            calculations = {}
            for profile in list_particle_profiles():
                particle_type = profile.particle_type
                factor = (
                    0.6 / (2 * math.pi)
                    if profile.data_structure.value == "grid_based"
                    else 1.0
                )
                psd = SizeDistribution(
                    [0.1 * factor, 0.3 * factor, 1.0 * factor, 3.0 * factor],
                    [1.0, 5.0, 5.0, 1.0],
                )
                result = compute_population(
                    particle_type,
                    sources[particle_type],
                    psd,
                    wavelength=0.6,
                    parameters=PROFILE_REQUESTS[particle_type],
                    truncation_policy="truncate",
                    check_convergence=False,
                )
                with self.subTest(profile=particle_type):
                    self.assertTrue(result.qa.passed, result.qa.errors)
                    self.assertGreater(result.bulk.extinction_coefficient, 0)
                    self.assertEqual(
                        result.members[0].interpolation_provenance["method"],
                        "multilinear",
                    )
                    self.assertTrue(
                        result.members[0].interpolation_provenance["neighbors"]
                    )
                    self.assertEqual(
                        result.bulk.metadata["bulk_coefficient_unit"], "m-1"
                    )
                calculations[particle_type] = (result,)

            scheme = BulkDataset(
                "phase11_all_profiles",
                (0.6,),
                calculations,
            )
            netcdf_path = _write_dataset(root / "all_profiles.nc", scheme, format='netcdf4')
            hdf5_path = _write_dataset(root / "all_profiles.h5", scheme, format='hdf5')
            netcdf_report = validate_file(netcdf_path)
            hdf5_report = validate_file(hdf5_path)
            netcdf = read(netcdf_path)
            hdf5 = read(hdf5_path)

        self.assertTrue(netcdf_report.passed, netcdf_report.errors)
        self.assertTrue(hdf5_report.passed, hdf5_report.errors)
        self.assertEqual(len(netcdf_report.components), 8)
        self.assertEqual(set(netcdf["components"]), set(hdf5["components"]))
        for component in netcdf["components"]:
            for variable in (
                "wavelength",
                "beta_ext",
                "beta_sca",
                "beta_abs",
                "ssa",
                "g",
            ):
                self.assertEqual(
                    netcdf["components"][component]["datasets"][variable]["data"],
                    hdf5["components"][component]["datasets"][variable]["data"],
                    f"{component}/{variable}",
                )

    def test_every_profile_exact_node_integrates_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            sources = create_all_profile_fixtures(Path(directory) / "l1")
            for profile in list_particle_profiles():
                particle_type = profile.particle_type
                factor = (
                    0.5 / (2 * math.pi)
                    if profile.data_structure.value == "grid_based"
                    else 1.0
                )
                result = compute_population(
                    particle_type,
                    sources[particle_type],
                    SizeDistribution(
                        [0.1 * factor, 0.5 * factor, 2.0 * factor],
                        [1.0, 6.0, 1.0],
                    ),
                    wavelength=0.5,
                    parameters=EXACT_PROFILE_REQUESTS[particle_type],
                    truncation_policy="truncate",
                    check_convergence=False,
                )
                with self.subTest(profile=particle_type):
                    provenance = result.members[0].interpolation_provenance
                    self.assertEqual(provenance["method"], "exact")
                    self.assertEqual(len(provenance["neighbors"]), 1)
                    self.assertAlmostEqual(
                        provenance["neighbors"][0]["weight"], 1.0
                    )
                    self.assertGreater(result.bulk.extinction_coefficient, 0)
                    self.assertTrue(result.qa.passed, result.qa.errors)


if __name__ == "__main__":
    unittest.main()
