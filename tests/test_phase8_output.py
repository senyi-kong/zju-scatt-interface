import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from zju_scatt_interface.bulk.models import BulkDataset, EnsembleMemberResult, PopulationResult
from zju_scatt_interface.bulk.quality import BulkConvergenceReport, BulkQualityReport
from zju_scatt_interface.io.canonical import OutputOptions, read, validate_file
from zju_scatt_interface.io.canonical import _write_dataset as _write_dataset
from zju_scatt_interface.io.canonical import _write_optics as _write_optics
from zju_scatt_interface.io.canonical import _write_population as _write_population
from zju_scatt_interface.optics.models import BulkOptics
from zju_scatt_interface.psd.models import RemapReport


def calculation(wavelength, scale=1.0, *, temperature=220.0):
    phase = [
        [
            [1.0, 0.1, 0.0, 0.0],
            [0.1, 0.8, 0.0, 0.0],
            [0.0, 0.0, 0.7, -0.05],
            [0.0, 0.0, 0.05, 0.6],
        ]
        for _ in range(3)
    ]
    metadata = {
        "psd": {
            "size": [0.1, 1.0, 10.0],
            "dndr": [1.0, 2.0, 1.0],
            "size_unit": "um",
            "dndr_unit": "cm-3",
            "size_definition": "volume_equivalent_sphere_radius",
            "integration_mode": "discrete_bin",
            "source": "python_array",
        },
        "scattering_angles_degrees": [0.0, 90.0, 180.0],
    }
    bulk = BulkOptics(
        10.0 * scale,
        8.0 * scale,
        2.0 * scale,
        0.8,
        0.4,
        phase,
        4.0,
        3,
        metadata,
    )
    qa = BulkQualityReport(True, {"extinction_closure": True}, {"error": 0.0})
    convergence = BulkConvergenceReport(
        True,
        True,
        0.05,
        3,
        2,
        {"extinction_coefficient": 0.01},
        "passed",
    )
    remap = RemapReport(4.0, 4.0, 0.0, 0.0, "error", (0.1, 10.0), (0.1, 10.0))
    member = EnsembleMemberResult(
        {"temperature_k": temperature, "smoothness": 2.5},
        1.0,
        bulk,
        remap,
        qa,
        convergence,
        {"method": "linear", "source_files": ["source.nc"]},
    )
    return PopulationResult(
        "super_spheroid_ice",
        wavelength,
        bulk,
        qa,
        (member,),
        {"members": 1},
        {"source": "test"},
    )


def scheme_result():
    return BulkDataset(
        "Phase 8 test scheme",
        (0.67, 1.0),
        {"ice": (calculation(0.67), calculation(1.0, 2.0))},
    )


class Phase8RoundTripTests(unittest.TestCase):
    def test_ensemble_member_coordinate_has_explicit_integer_indices(self):
        import h5py
        import numpy as np
        from netCDF4 import Dataset

        result = calculation(1.6)
        result.members = tuple(replace(result.members[0], weight=1/3,
            parameters={"n": n, "asp": asp, "mr": 1.5, "mi": 0.003})
            for n, asp in ((2.7, 1.5), (2.8, 1.9), (2.5, 1.3)))
        with tempfile.TemporaryDirectory() as directory:
            path = _write_population(Path(directory) / "ensemble.nc", result, format='netcdf4')
            h5path = _write_population(Path(directory) / "ensemble.h5", result, format='hdf5')
            with Dataset(path) as handle:
                group = next(iter(handle.groups.values()))
                index = group.variables["ensemble_member"]
                self.assertEqual(index.dtype, np.dtype("int32"))
                np.testing.assert_array_equal(index[:], [0, 1, 2])
                np.testing.assert_array_equal(group.variables["ssph_asp"][0], [1.5, 1.9, 1.3])
                np.testing.assert_allclose(group.variables["shape_weight"][0], [1/3]*3)
            for file in (path, h5path):
                with h5py.File(file) as handle:
                    group = next(iter(handle.values()))
                    np.testing.assert_array_equal(group["ensemble_member"][:], [0, 1, 2])

    def setUp(self):
        try:
            import h5py  # noqa: F401
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("h5py and netCDF4 are required")

    def test_netcdf_and_hdf5_have_equivalent_canonical_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nc_path = _write_dataset(
                root / "scheme.nc",
                scheme_result(),
                source_manifest={"files": ["source.nc"]},
            format='netcdf4')
            h5_path = _write_dataset(
                root / "scheme.h5",
                scheme_result(),
                source_manifest={"files": ["source.nc"]},
            format='hdf5')
            netcdf = read(nc_path)
            hdf5 = read(h5_path)
            nc_report = validate_file(nc_path)
            h5_report = validate_file(h5_path)

        self.assertTrue(nc_report.passed, nc_report.errors)
        self.assertTrue(h5_report.passed, h5_report.errors)
        self.assertEqual(nc_report.components, ("ice",))
        for name, nc_variable in netcdf["components"]["ice"]["datasets"].items():
            h5_variable = hdf5["components"]["ice"]["datasets"][name]
            self.assertEqual(nc_variable["data"], h5_variable["data"], name)
            self.assertEqual(nc_variable["dimensions"], h5_variable["dimensions"])
            self.assertEqual(nc_variable["units"], h5_variable["units"])
        self.assertEqual(
            netcdf["components"]["ice"]["attributes"]["particle_type"],
            "super_spheroid_ice",
        )
        self.assertEqual(
            netcdf["components"]["ice"]["datasets"]["p43"]["data"][0],
            [0.05, 0.05, 0.05],
        )
        self.assertEqual(
            netcdf["components"]["ice"]["datasets"]["temperature"]["units"], "K"
        )

    def test_single_particle_calculation_has_independent_output_writers(self):
        calculations = (calculation(0.67), calculation(1.0, 2.0))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nc_path = _write_population(
                root / "ice.nc", calculations, component_name="ice"
            , format='netcdf4')
            h5_path = _write_population(
                root / "ice.h5", calculations, component_name="ice"
            , format='hdf5')
            netcdf = read(nc_path)
            hdf5 = read(h5_path)
        self.assertEqual(set(netcdf["components"]), {"ice"})
        self.assertEqual(set(hdf5["components"]), {"ice"})
        self.assertNotIn("mixture", netcdf["components"])
        self.assertEqual(
            netcdf["components"]["ice"]["datasets"]["beta_ext"]["data"],
            hdf5["components"]["ice"]["datasets"]["beta_ext"]["data"],
        )

    def test_standard_shape_and_index_names_without_outer_wavelength(self):
        result = calculation(1.6)
        result.members[0].parameters = {"roundness": 2.0, "aspect_ratio": 1.6,
                                       "refractive_index_real": 1.5, "refractive_index_imaginary": 0.003}
        with tempfile.TemporaryDirectory() as directory:
            path = _write_population(Path(directory) / "bulk.nc", result, format='netcdf4')
            content = read(path)
            self.assertEqual(content["datasets"], {})
            group = next(iter(content["components"].values()))["datasets"]
            for name, value in (("ssph_n", 2), ("ssph_asp", 1.6), ("mr", 1.5), ("mi", 0.003)):
                self.assertEqual(group[name]["data"], [[value]])
            for name in ("roundness", "aspect_ratio", "refractive_index_real", "refractive_index_imaginary",
                         "qa_passed", "convergence_passed", "interpolation_provenance", "quality_report",
                         "uncertainty", "psd_remap_report"):
                self.assertNotIn(name, group)
            self.assertTrue(validate_file(path).passed)
    def test_custom_bulk_optical_result_can_be_written_directly(self):
        custom = calculation(0.67).bulk
        custom.metadata["particle_type"] = "super_spheroid_ice"
        with tempfile.TemporaryDirectory() as directory:
            path = _write_optics(
                Path(directory) / "weighted_ice.nc",
                [0.67],
                [custom],
                component_name="weighted_ice_shapes",
            format='netcdf4')
            content = read(path)
        self.assertEqual(set(content["components"]), {"weighted_ice_shapes"})
        self.assertEqual(
            content["components"]["weighted_ice_shapes"]["datasets"]["beta_ext"][
                "data"
            ],
            [10.0],
        )

    def test_scientific_arrays_and_compression_exclude_diagnostics(self):
        import h5py
        from netCDF4 import Dataset

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nc_path = _write_dataset(
                root / "compressed.nc",
                scheme_result(),
                options=OutputOptions(
                    compression=True,
                    compression_level=6,
                    chunk_wavelength=1,
                ),
            )
            h5_path = _write_dataset(
                root / "compressed.hdf5",
                scheme_result(),
                options=OutputOptions(
                    compression=True,
                    compression_level=6,
                    chunk_wavelength=1,
                ),
            )
            with Dataset(nc_path) as handle:
                self.assertNotIn("wavelength", handle.variables)
                group = handle.groups["ice"]
                self.assertTrue(group.variables["beta_ext"].filters()["zlib"])
                self.assertEqual(group.variables["beta_ext"].chunking(), [1])
                self.assertEqual(group.variables["psd_dndr"].units, "cm-3")
                self.assertEqual(group.size_definition, "volume_equivalent_sphere_radius")
                self.assertIn("ssph_n", group.variables)
                for name in ("qa_passed", "convergence_passed", "interpolation_provenance",
                             "quality_report", "uncertainty", "psd_remap_report", "smoothness"):
                    self.assertNotIn(name, group.variables)
            with h5py.File(h5_path) as handle:
                group = handle["ice"]
                self.assertEqual(group["beta_ext"].compression, "gzip")
                self.assertEqual(group["beta_ext"].chunks, (1,))
                self.assertNotIn("wavelength", handle)
                for name in ("qa_passed", "convergence_passed", "interpolation_provenance",
                             "quality_report", "uncertainty", "psd_remap_report"):
                    self.assertNotIn(name, group)

    def test_atomic_failure_preserves_existing_target_and_removes_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "existing.h5"
            target.write_bytes(b"original")

            def fail(path, schema, options):
                path.write_bytes(b"incomplete")
                raise RuntimeError("simulated writer failure")

            with patch(
                'zju_scatt_interface.io.canonical._hdf5_write_schema',
                side_effect=fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    _write_dataset(target, scheme_result(), format='hdf5')

            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_validator_detects_extinction_closure_corruption(self):
        import h5py

        with tempfile.TemporaryDirectory() as directory:
            target = _write_dataset(
                Path(directory) / "corrupt.h5", scheme_result()
            , format='hdf5')
            with h5py.File(target, "r+") as handle:
                handle["ice"]["beta_ext"][0] = 99.0
            report = validate_file(target)

        self.assertFalse(report.passed)
        self.assertTrue(any("closure" in error for error in report.errors))

    def test_bare_optics_use_explicit_wavelengths(self):
        from zju_scatt_interface.io import write
        optics = BulkOptics(10.0, 8.0, 2.0, 0.8, 0.4)
        with tempfile.TemporaryDirectory() as directory:
            path = write(optics, Path(directory) / "bare.nc", wavelength_um=0.55)
            report = validate_file(path)
        self.assertTrue(report.passed, report.errors)
        self.assertTrue(any("PSD" in warning for warning in report.warnings))


if __name__ == "__main__":
    unittest.main()
