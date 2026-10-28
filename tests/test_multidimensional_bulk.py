import tempfile
import unittest
from pathlib import Path

from tests.test_bulk_pipeline import create_source
from zju_scatt_interface.bulk.grid import (
    BulkDimension,
    MultiBulkScheme,
    SingleBulkScheme,
    build_grid,
    build_grids,
    load_grid_scheme,
)
from zju_scatt_interface.config.scheme import ParticleComponent
from zju_scatt_interface.io.canonical import _write_grid as _write_grid
from zju_scatt_interface.io.canonical import read, validate_file


def component(particle_type: str, *, name: str) -> ParticleComponent:
    shape = {"relative_humidity": 0.0} if "sulfate" in particle_type else {}
    return ParticleComponent.from_mapping(
        {
            "name": name,
            "particle_type": particle_type,
            "size_distribution": {
                "size": [0.1, 1.0, 10.0],
                "dndr": [1.0, 8.0, 1.0],
            },
            "shape_parameters": shape,
            "refractive_index": {"mode": "database"},
        }
    )


class MultidimensionalBulkTests(unittest.TestCase):
    def setUp(self):
        try:
            import h5py  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("h5py and netCDF4 are required")

    def test_single_particle_grid_retains_declared_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "sphere_sulfate"
            for wavelength in (0.5, 0.7):
                create_source(
                    sources
                    / f"L1_sphere_sulfate_wl_{wavelength:.3f}_um_ref_1.5_0.nc",
                    wavelength=wavelength,
                    rh=[0, 50],
                    phase=True,
                )
            scheme = SingleBulkScheme(
                "sulfate_grid",
                component("sphere_sulfate", name="sulfate_grid"),
                (
                    BulkDimension(
                        "wavelength", (0.5, 0.6), unit="um"
                    ),
                    BulkDimension(
                        "relative_humidity", (0.0, 0.5), unit="1"
                    ),
                ),
            )
            result = build_grid(
                scheme,
                source_paths=sources,
                truncation_policy="truncate",
                include_phase_matrix=True,
                target_angles_degrees=[0.0, 90.0, 180.0],
            )
            nc_path = _write_grid(
                root / "sulfate_grid.nc", result, scheme=scheme
            , format='netcdf4')
            h5_path = _write_grid(
                root / "sulfate_grid.h5", result, scheme=scheme
            , format='hdf5')
            netcdf = read(nc_path)
            hdf5 = read(h5_path)
            nc_report = validate_file(nc_path)
            h5_report = validate_file(h5_path)

        self.assertEqual(result.shape, (2, 2))
        self.assertEqual(len(result.calculations), 4)
        self.assertEqual(
            [value.wavelength_um for value in result.calculations],
            [0.5, 0.5, 0.6, 0.6],
        )
        self.assertTrue(nc_report.passed, nc_report.errors)
        self.assertTrue(h5_report.passed, h5_report.errors)
        for content in (netcdf, hdf5):
            datasets = content["components"]["sulfate_grid"]["datasets"]
            self.assertEqual(datasets["wavelength"]["data"], [0.5, 0.6])
            self.assertEqual(
                datasets["relative_humidity"]["data"], [0.0, 0.5]
            )
            self.assertEqual(
                datasets["beta_ext"]["dimensions"],
                ["wavelength", "relative_humidity"],
            )
            self.assertEqual(len(datasets["beta_ext"]["data"]), 2)
            self.assertEqual(len(datasets["beta_ext"]["data"][0]), 2)
            self.assertEqual(
                datasets["p11"]["dimensions"],
                ["wavelength", "relative_humidity", "sca_angle"],
            )
            self.assertEqual(len(datasets["p11"]["data"][0][0]), 3)

    def test_multi_scheme_builds_different_particle_grids_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cloud_sources = root / "sphere_water_cloud"
            sulfate_sources = root / "sphere_sulfate"
            for wavelength in (0.5, 0.7):
                create_source(
                    cloud_sources
                    / f"L1_sphere_water_cloud_wl_{wavelength:.3f}_um_ref_1.3_0.nc",
                    wavelength=wavelength,
                )
                create_source(
                    sulfate_sources
                    / f"L1_sphere_sulfate_wl_{wavelength:.3f}_um_ref_1.5_0.nc",
                    wavelength=wavelength,
                    rh=[0, 50],
                )
            cloud = SingleBulkScheme(
                "cloud",
                component("sphere_water_cloud", name="cloud"),
                (BulkDimension("wavelength", (0.5, 0.6), unit="um"),),
            )
            sulfate = SingleBulkScheme(
                "sulfate",
                component("sphere_sulfate", name="sulfate"),
                (
                    BulkDimension("wavelength", (0.5,), unit="um"),
                    BulkDimension("relative_humidity", (0.0, 0.5)),
                ),
            )
            scheme = MultiBulkScheme("multi_grid", (cloud, sulfate))
            result = build_grids(
                scheme,
                source_paths={
                    "cloud": cloud_sources,
                    "sulfate": sulfate_sources,
                },
                truncation_policy="truncate",
            )
        self.assertEqual(set(result.components), {"cloud", "sulfate"})
        self.assertEqual(result.components["cloud"].shape, (2,))
        self.assertEqual(result.components["sulfate"].shape, (1, 2))

    def test_dimension_size_and_wavelength_contracts_are_validated(self):
        with self.assertRaisesRegex(ValueError, "declares size"):
            BulkDimension.from_mapping(
                {"name": "temperature", "size": 3, "coordinates": [220, 270]}
            )
        with self.assertRaisesRegex(ValueError, "exactly one wavelength"):
            SingleBulkScheme(
                "invalid",
                component("sphere_water_cloud", name="invalid"),
                (BulkDimension("temperature", (220.0,), unit="K"),),
            )

    def test_python_multidimensional_scheme_loads_declared_shapes(self):
        path = (
            Path(__file__).parents[1]
            / "configs"
            / "multidimensional_bulk_scheme.example.py"
        )
        scheme = load_grid_scheme(path)
        self.assertEqual([item.name for item in scheme.particles], ["ice", "sulfate"])
        self.assertEqual(scheme.particles[0].shape, (2, 2, 2, 2))
        self.assertEqual(scheme.particles[0].point_count, 16)
        self.assertEqual(scheme.particles[1].shape, (2, 3))


if __name__ == "__main__":
    unittest.main()
