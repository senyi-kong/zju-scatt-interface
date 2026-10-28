
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import zju_scatt_interface.access.metadata as _domain_access_metadata
from tests.local_data import local_l1_root
from zju_scatt_interface.sources.adapters.black_carbon import BlackCarbonGridAdapter
from zju_scatt_interface.sources.adapters.boundaries import AdapterError
from zju_scatt_interface.sources.adapters.ice import IceWavelengthTemperatureAdapter
from zju_scatt_interface.sources.adapters.registry import (
    get_particle_adapter,
    interpolate_particle,
    resolve_particle_sources,
    resolve_plan_component_sources,
)
from zju_scatt_interface.sources.adapters.sea_salt import SeaSaltWavelengthAdapter
from zju_scatt_interface.sources.adapters.spheres import (
    HygroscopicSphereAdapter,
    WaterCloudWavelengthAdapter,
)
from zju_scatt_interface.sources.adapters.super_spheroid import SuperSpheroidGridAdapter


def create_l1(
    path: Path,
    *,
    wavelength: float | None,
    rh=None,
    vf=None,
    df=False,
):
    from netCDF4 import Dataset

    path.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(path, "w") as dataset:
        dataset.createDimension("xsize_veq", 2)
        if wavelength is not None:
            dataset.createVariable("wavelength", "f8")[:] = wavelength
            raw_size = [2 * math.pi / wavelength, 4 * math.pi / wavelength]
        else:
            raw_size = [1.0, 2.0]
        dataset.createVariable("xsize_veq", "f8", ("xsize_veq",))[:] = raw_size
        dimensions = []
        if df:
            dataset.createDimension("Df", 1)
            dataset.createVariable("Df", "f8", ("Df",))[:] = [1.8]
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
        import numpy as np

        values = np.arange(1, math.prod(shape) + 1, dtype=float).reshape(shape)
        dataset.createVariable("cext", "f8", tuple(dimensions))[:] = values
        dataset.createVariable("ssa", "f8", tuple(dimensions))[:] = 0.7
        dataset.createVariable("g", "f8", tuple(dimensions))[:] = 0.3


class AdapterContractTests(unittest.TestCase):
    def setUp(self):
        try:
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("netCDF4 is not installed")

    def test_registry_dispatches_all_adapter_families(self):
        self.assertIsInstance(get_particle_adapter("bc"), BlackCarbonGridAdapter)
        self.assertIsInstance(get_particle_adapter("dust"), SuperSpheroidGridAdapter)
        self.assertIsInstance(get_particle_adapter("sea_salt"), SeaSaltWavelengthAdapter)
        self.assertIsInstance(get_particle_adapter("ice"), IceWavelengthTemperatureAdapter)
        self.assertIsInstance(
            get_particle_adapter("sulfate"), HygroscopicSphereAdapter
        )
        self.assertIsInstance(
            get_particle_adapter("water_cloud"), WaterCloudWavelengthAdapter
        )

    def test_water_cloud_resolves_two_wavelength_neighbors_and_interpolates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sphere_water_cloud"
            paths = []
            for wavelength in (0.5, 0.7):
                path = root / (
                    f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_"
                    "ref_1.3_1e-8.nc"
                )
                create_l1(path, wavelength=wavelength)
                paths.append(path)
            resolution = resolve_particle_sources(
                "water_cloud", root, wavelength=600.0, wavelength_unit="nm"
            )
            product = resolution.interpolate()
        self.assertEqual(len(resolution.sources), 2)
        self.assertEqual(resolution.target_coordinates, {"wavelength": 0.6})
        self.assertEqual(product.provenance.method, "multilinear")
        self.assertEqual(
            product.provenance.adapter["adapter"], "WaterCloudWavelengthAdapter"
        )

    def test_hygroscopic_sphere_converts_rh_and_selects_four_corners(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sphere_sulfate"
            for wavelength in (0.5, 0.7):
                create_l1(
                    root
                    / f"L1_sphere_sulfate_wl_{wavelength:.3f}_um_ref_1.5_1e-8.nc",
                    wavelength=wavelength,
                    rh=[0, 50],
                )
            resolution = resolve_particle_sources(
                "sulfate",
                root,
                wavelength=0.6,
                parameters={"RH": 0.25},
            )
        self.assertEqual(len(resolution.sources), 4)
        self.assertEqual(
            {item.coordinate_indices["rh"] for item in resolution.sources},
            {0, 1},
        )
        self.assertIn(
            "source RH converted from percent to unit 1",
            resolution.provenance.coordinate_conversions,
        )

    def test_sea_salt_branch_mapping_and_default_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "coated_super_spheroid_seasalt"
            path = root / (
                "L1_coated_super_spheroid_seasalt_multiparas_"
                "wl_00.700_um_ref_1.49_2e-7.nc"
            )
            create_l1(path, wavelength=0.7, rh=[-50, 50, 80])
            crystal = resolve_particle_sources(
                "sea_salt",
                root,
                wavelength=0.7,
                parameters={
                    "relative_humidity": 0.5,
                    "humidity_branch": "crystallization",
                },
            )
            default = resolve_particle_sources(
                "sea_salt",
                root,
                wavelength=0.7,
                parameters={"relative_humidity": 0.5},
            )
        self.assertEqual(crystal.sources[0].coordinate_indices, {"rh": 0})
        self.assertEqual(default.sources[0].coordinate_indices, {"rh": 1})
        self.assertEqual(
            default.provenance.defaults_applied,
            ["humidity_branch=deliquescence"],
        )

    def test_grid_adapters_use_native_refractive_index_not_wavelength_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dust = root / "super_spheroid" / (
                "L1_super_spheroid_n_2.000_asp_1.000_wl_nan_"
                "ref_1.500e+00_1.000e-02.nc"
            )
            create_l1(dust, wavelength=None)
            dust_resolution = resolve_particle_sources(
                "dust",
                dust,
                wavelength=0.55,
                parameters={
                    "mr": 1.5,
                    "mi": 0.01,
                    "smoothness": 2.0,
                    "alpha": 1.0,
                },
            )

            bc = root / "encapsulated_fractal_aggregates_black_carbon" / (
                "L1_encapsulated_fractal_aggregates_black_carbon_df_1.80_"
                "wl_nan_ref_bc_1.650e+00_5.500e-01_hygro_1.200e+00_1.000e-03.nc"
            )
            create_l1(bc, wavelength=None, vf=[0.1, 0.5], df=True)
            bc_resolution = resolve_particle_sources(
                "bc",
                bc,
                wavelength=0.55,
                parameters={
                    "bc_mr": 1.65,
                    "bc_mi": 0.55,
                    "hygro_mr": 1.2,
                    "hygro_mi": 0.001,
                    "Df": 1.8,
                    "Vf": 0.5,
                },
            )
        self.assertNotIn("wavelength", dust_resolution.target_coordinates)
        self.assertEqual(
            dust_resolution.provenance.refractive_index_input_mode,
            "explicit_refractive_index",
        )
        self.assertEqual(bc_resolution.sources[0].coordinate_indices["vf"], 1)
        self.assertEqual(bc_resolution.sources[0].wavelength_um, 0.55)

    def test_wavelength_labelled_bc_source_keeps_its_native_wavelength(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "encapsulated_fractal_aggregates_black_carbon" / (
                "L1_encapsulated_fractal_aggregates_black_carbon_df_2.10_"
                "wl_10.000_um_ref_bc_3.057e+00_2.117e+00_"
                "hygro_1.820e+00_9.000e-02_v1.2.2_20260616.nc"
            )
            create_l1(path, wavelength=10.0, vf=[0.1, 0.5], df=True)
            resolution = resolve_particle_sources(
                "bc",
                path,
                wavelength=10.0,
                parameters={
                    "database_type": "wavelength",
                    "ri_scheme": "v1.2.2",
                    "Df": 2.1,
                    "Vf": 0.5,
                },
            )
        self.assertIsNone(resolution.sources[0].wavelength_um)

    def test_ice_coordinates_and_size_definition_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "super_spheroid_ice"
            path = root / (
                "L1_super_spheroid_ice_n_2.000_asp_1.250_wl_10.000_um_"
                "ref_1.3_0.1_t_220k.nc"
            )
            create_l1(path, wavelength=10.0)
            resolution = resolve_particle_sources(
                "ice",
                root,
                wavelength=1000,
                wavelength_unit="cm-1",
                parameters={"temperature_k": 220, "n": 2.0, "asp": 1.25},
                size_definition="volume_equivalent_sphere_radius",
            )
        self.assertEqual(
            resolution.target_coordinates,
            {
                "wavelength": 10.0,
                "temperature": 220.0,
                "roundness": 2.0,
                "aspect_ratio": 1.25,
            },
        )
        self.assertEqual(resolution.sources[0].size_dataset, "xsize_veq")

    def test_ice_temperature_interpolates_250k_and_returns_nan_outside_support(self):
        from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryWarning

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "super_spheroid_ice"
            for temperature in (220, 270):
                path = root / (
                    f"L1_super_spheroid_ice_n_2.000_asp_1.000_wl_1.600_um_"
                    f"ref_1.3_0.1_t_{temperature}k.nc"
                )
                create_l1(path, wavelength=1.6)
            parameters = {"temperature": 250, "n": 2.0, "asp": 1.0}
            resolution = resolve_particle_sources("ice", root, wavelength=1.6, parameters=parameters)
            self.assertEqual({item.coordinates["temperature"] for item in resolution.sources}, {220, 270})
            product = interpolate_particle("ice", root, wavelength=1.6, parameters=parameters, target_size_um=[1.0])
            self.assertTrue(all(math.isfinite(value) for value in product.optics.extinction_cross_section))
            for temperature in (110, 300):
                with self.subTest(temperature=temperature), self.assertWarns(DatabaseBoundaryWarning):
                    product = interpolate_particle(
                        "ice", root, wavelength=1.6,
                        parameters={"temperature_k": temperature, "n": 2.0, "asp": 1.0},
                        target_size_um=[1.0, 2.0], target_angles_degrees=[0, 90, 180],
                    )
                self.assertEqual(product.coordinates["temperature"], temperature)
                self.assertEqual(product.coordinates["wavelength"], 1.6)
                self.assertTrue(all(math.isnan(value) for value in product.optics.extinction_cross_section))
                self.assertEqual(product.provenance.method, "out_of_database_bounds")

    def test_profile_validation_rejects_invalid_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sphere_water_cloud"
            path = root / "L1_sphere_water_cloud_wl_0.500_um_ref_1.3_0.nc"
            create_l1(path, wavelength=0.5)
            with self.assertRaisesRegex(AdapterError, "wavelength only"):
                resolve_particle_sources(
                    "water_cloud",
                    root,
                    wavelength=0.5,
                    parameters={"mr": 1.33},
                )
            with self.assertRaisesRegex(AdapterError, "No extrapolation"):
                resolve_particle_sources("water_cloud", root, wavelength=0.7)

    def test_verified_dependency_plan_paths_connect_to_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sphere_water_cloud"
            path = root / "L1_sphere_water_cloud_wl_0.500_um_ref_1.3_0.nc"
            create_l1(path, wavelength=0.5)
            source = SimpleNamespace(
                component_names=("cloud",),
                particle_type="sphere_water_cloud",
                cache_path=path,
                ready=True,
                status="ready",
            )
            resolution = resolve_plan_component_sources(
                SimpleNamespace(sources=(source,)),
                "cloud",
                wavelength=0.5,
            )
            source.ready = False
            source.status = "missing"
            with self.assertRaisesRegex(AdapterError, "not ready"):
                resolve_plan_component_sources(
                    SimpleNamespace(sources=(source,)),
                    "cloud",
                    wavelength=0.5,
                )
        self.assertEqual(resolution.provenance.selected_node_count, 1)


class LocalL1AdapterRegressionTests(unittest.TestCase):
    def test_all_eight_local_families_resolve_and_load_exact_nodes(self):
        root = local_l1_root()
        if not root.exists():
            self.skipTest("Local ZJU-SCATT L1 database is not mounted")

        cases = []
        water = next((root / "sphere_water_cloud").rglob("*.nc"))
        water_meta = _domain_access_metadata.extract_scatt_metadata(water.name)
        cases.append(("water_cloud", water, water_meta["wavelength_um"], {}))

        for family in ("sphere_sulfate", "sphere_nitrate", "sphere_organic_carbon"):
            path = next((root / family).rglob("*.nc"))
            meta = _domain_access_metadata.extract_scatt_metadata(path.name)
            cases.append((family, path, meta["wavelength_um"], {"rh": 0.0}))

        sea = next((root / "coated_super_spheroid_seasalt").rglob("*.nc"))
        sea_meta = _domain_access_metadata.extract_scatt_metadata(sea.name)
        cases.append(
            (
                "sea_salt",
                sea,
                sea_meta["wavelength_um"],
                {"rh": 0.75, "humidity_branch": "crystallization"},
            )
        )

        ice = next((root / "super_spheroid_ice").rglob("*.nc"))
        ice_meta = _domain_access_metadata.extract_scatt_metadata(ice.name)
        cases.append(
            (
                "ice",
                ice,
                ice_meta["wavelength_um"],
                {
                    "temperature": ice_meta["temperature_k"],
                    "roundness": ice_meta["n"],
                    "aspect_ratio": ice_meta["aspect_ratio"],
                },
            )
        )

        dust = next((root / "super_spheroid").rglob("*.nc"))
        dust_meta = _domain_access_metadata.extract_scatt_metadata(dust.name)
        cases.append(
            (
                "dust",
                dust,
                0.55,
                {
                    "mr": dust_meta["ref_real"],
                    "mi": dust_meta["ref_imag"],
                    "roundness": dust_meta["n"],
                    "aspect_ratio": dust_meta["aspect_ratio"],
                },
            )
        )

        bc = next(
            (root / "encapsulated_fractal_aggregates_black_carbon").rglob("*.nc")
        )
        cases.append(
            (
                "bc",
                bc,
                0.55,
                {
                    "bc_mr": 1.65,
                    "bc_mi": 0.55,
                    "hygro_mr": 1.2,
                    "hygro_mi": 0.001,
                    "df": 1.8,
                    "vf": 0.010973936878144741,
                },
            )
        )

        products = [
            interpolate_particle(
                particle_type,
                path,
                wavelength=wavelength,
                parameters=parameters,
            )
            for particle_type, path, wavelength, parameters in cases
        ]
        self.assertEqual(len(products), 8)
        self.assertTrue(
            all(product.provenance.method == "exact" for product in products)
        )
        self.assertTrue(
            all(product.optics.extinction_cross_section for product in products)
        )


if __name__ == "__main__":
    unittest.main()
