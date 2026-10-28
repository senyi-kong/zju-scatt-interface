"""Native format, normalization, safety and official-reference regressions."""

import copy
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from zju_scatt_interface.io.native import (
    arts_arrays_from_bulk,
    arts_output_template,
    bulk_model_fields,
    native_template_from_reference,
    read_native_optical_arrays,
    rttov13_aerosol_output_template,
    scalar_phase_to_model,
    write_native_optical_output,
)
from zju_scatt_interface.optics.models import BulkOptics

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "native_example", ROOT / "examples/example_17_native_model_formats.py"
)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class NativeOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Retain artifacts for inspection; do not recursively delete directories.
        cls.output = Path(tempfile.mkdtemp(prefix="zju-native-tests-"))
        cls.products = example.run_example(cls.output)

    def test_example_produces_all_models(self):
        import h5py
        from netCDF4 import Dataset

        self.assertEqual(len(self.products), 4)
        arts = read_native_optical_arrays(self.output / "arts_ssd.xml", model="arts2")
        self.assertEqual(arts["pha_mat_data"].shape, (2, 1, 181, 1, 1, 1, 6))
        self.assertTrue(np.all(np.diff(arts["f_grid"]) > 0))
        with Dataset(self.output / "CloudCoeff.nc") as f:
            self.assertEqual(f.data_model, "NETCDF3_CLASSIC")
            self.assertEqual(f.Release, 3)
            self.assertEqual(
                f["ke_IR"].dimensions, ("n_IR_Densities", "n_IR_Radii", "n_IR_Frequencies")
            )
        with h5py.File(self.output / "scaercoef_demo.H5") as f:
            self.assertEqual(f["SCAER/DATA/LEGCOEF"].shape, (2, 1, 1, 33))
            np.testing.assert_array_equal(f["SCAER/DATA/LEGCOEF"].attrs["UBOUND"], [33, 1, 1, 2])

    def test_arts_conversion_preserves_cross_sections_and_phase_sign(self):
        bulk, scheme, _ = example.calculate_fixture()
        for matrix in bulk.phase_matrix:
            matrix[3][2] = 0.1
            matrix[2][3] = -0.1
        arrays = arts_arrays_from_bulk(
            scheme, component="demo", number_density_m3=3e6, temperature_k=250
        )
        np.testing.assert_allclose(arrays["ext_mat_data"], bulk.extinction_coefficient / 3e6)
        np.testing.assert_allclose(
            arrays["pha_mat_data"][..., 4], -0.1 * bulk.scattering_coefficient / (3e6 * 4 * np.pi)
        )

    def test_unit_conversions(self):
        bulk = BulkOptics(10, 8, 2, 0.8, 0.4)
        self.assertEqual(
            bulk_model_fields(bulk, model="rttov13", number_density_m3=2e6), {"ABS": 1, "SCA": 4}
        )
        self.assertEqual(
            bulk_model_fields(bulk, model="crtm-cloud-v3", mass_concentration_kg_m3=0.5),
            {"ke": 20, "w": 0.8, "g": 0.4},
        )
        with self.assertRaises(ValueError):
            bulk_model_fields(bulk, model="crtm-cloud-v3")

    def test_phase_projection_against_analytic_anisotropic_integral(self):
        angles = np.linspace(0, 180, 181)
        phase = 1 + 0.6 * np.cos(np.deg2rad(angles))
        result = scalar_phase_to_model(
            angles,
            phase,
            model="rttov13",
            max_moments=32,
            quadrature_points=96,
            hemisphere_points=12,
        )
        np.testing.assert_allclose(result["LEGCOEF"][:2], [1, 0.6], atol=1e-12)
        np.testing.assert_allclose(result["LEGCOEF"][2:], 0, atol=1e-12)
        self.assertAlmostEqual(result["BPR"], 0.425, places=12)
        result = scalar_phase_to_model(angles, phase, model="crtm-cloud-v3", quadrature_points=96)
        for offset in (0, 5, 12, 21):
            np.testing.assert_allclose(
                result["pcoeff"][offset : offset + 2], [0.5, 0.3], atol=1e-12
            )
        self.assertAlmostEqual(result["g"], 0.2, places=12)
        with self.assertRaisesRegex(ValueError, "not normalized"):
            scalar_phase_to_model(
                angles, phase * 2, model="rttov13", max_moments=16, quadrature_points=64
            )

    def test_official_crtm_binary_matches_byte_for_byte(self):
        reference = ROOT / "reference_data/rtm_formats/CloudCoeff_TAMU-07Sep2015.nc"
        binary = reference.with_suffix(".bin")
        if not binary.exists():
            self.skipTest("download official references first")
        arrays = read_native_optical_arrays(reference, model="crtm-cloud-v3")
        template = native_template_from_reference(reference, model="crtm-cloud-v3")
        template["format"] = "crtm-binary"
        target = write_native_optical_output(self.output / "official.bin", arrays, template)
        self.assertEqual(target.read_bytes(), binary.read_bytes())

    def test_official_arts_numeric_roundtrip(self):
        reference = ROOT / "reference_data/rtm_formats/ARTS_tmatrix.xml"
        if not reference.exists():
            self.skipTest("download official references first")
        arrays = read_native_optical_arrays(reference, model="arts2")
        template = native_template_from_reference(reference, model="arts2")
        target = write_native_optical_output(self.output / "official.xml", arrays, template)
        recovered = read_native_optical_arrays(target, model="arts2")
        for name in arrays:
            if isinstance(arrays[name], np.ndarray):
                np.testing.assert_array_equal(recovered[name], arrays[name])

    def test_crtm_endian_and_records_independently(self):
        source = self.output / "CloudCoeff.nc"
        template = native_template_from_reference(source, model="crtm-cloud-v3")
        arrays = read_native_optical_arrays(source, model="crtm-cloud-v3")
        template.update(format="crtm-binary", byte_order="big")
        path = write_native_optical_output(self.output / "big.bin", arrays, template)
        records = []
        with path.open("rb") as stream:
            while marker := stream.read(4):
                size = struct.unpack(">i", marker)[0]
                payload = stream.read(size)
                self.assertEqual(stream.read(4), marker)
                records.append(payload)
        self.assertEqual(len(records), 7)
        self.assertEqual(struct.unpack(">i", records[0]), (123456789,))
        self.assertEqual(struct.unpack(">8i", records[2]), (2, 2, 2, 2, 2, 3, 38, 1))
        values = np.frombuffer(records[4], dtype=">f8")
        np.testing.assert_array_equal(values[:8], arrays["ke_L_MW"].ravel())

    def test_reference_does_not_silently_supply_optics(self):
        template = native_template_from_reference(
            self.output / "CloudCoeff.nc", model="crtm-cloud-v3"
        )
        with self.assertRaisesRegex(ValueError, "missing source"):
            write_native_optical_output(self.output / "missing.nc", {}, template)

    def test_invalid_data_cannot_damage_existing_destination(self):
        target = self.output / "protected.xml"
        target.write_text("keep this", encoding="utf-8")
        bulk, scheme, _ = example.calculate_fixture()
        arrays = arts_arrays_from_bulk(
            scheme, component="demo", number_density_m3=3e6, temperature_k=250
        )
        arrays["ext_mat_data"][0] = np.nan
        with self.assertRaisesRegex(ValueError, "non-finite"):
            write_native_optical_output(
                target, arrays, arts_output_template(2, 1, 181), overwrite=True
            )
        self.assertEqual(target.read_text(), "keep this")

    def test_no_implicit_broadcast_or_integer_truncation(self):
        template = {
            "schema_version": 1,
            "model": "custom",
            "format": "hdf5",
            "variables": {"data": {"source": "x", "shape": [2], "dtype": "int32"}},
        }
        with self.assertRaisesRegex(ValueError, "expected shape"):
            write_native_optical_output(self.output / "bad.h5", {"x": 1}, template)
        with self.assertRaisesRegex(ValueError, "cannot be represented"):
            write_native_optical_output(self.output / "bad.h5", {"x": [1.1, 2]}, template)

    def test_custom_json_transpose_scale_groups(self):
        import h5py

        template = {
            "schema_version": 1,
            "model": "custom",
            "format": "hdf5",
            "variables": {
                "optics/ext": {
                    "source": "beta",
                    "shape": [3, 2],
                    "dtype": "float64",
                    "transpose": [1, 0],
                    "scale": 1000,
                    "attributes": {"units": "km-1"},
                }
            },
        }
        path = self.output / "custom.json"
        path.write_text(json.dumps(template))
        original = np.arange(6).reshape(2, 3)
        target = write_native_optical_output(self.output / "custom.h5", {"beta": original}, path)
        with h5py.File(target) as f:
            np.testing.assert_array_equal(f["optics/ext"][:], original.T * 1000)
        with self.assertRaises(FileExistsError):
            write_native_optical_output(target, {"beta": original}, path)

    def test_rttov_fortran_bounds_rejected(self):
        source = self.output / "scaercoef_demo.H5"
        template = native_template_from_reference(source, model="rttov13")
        arrays = read_native_optical_arrays(source, model="rttov13")
        template["variables"]["SCAER/DATA/LEGCOEF"]["attributes"]["UBOUND"] = [2, 1, 1, 33]
        with self.assertRaisesRegex(ValueError, "Fortran bounds"):
            write_native_optical_output(self.output / "wrong.H5", arrays, template)

    def test_crtm_phase_packing_and_axis_order_rejected(self):
        source = self.output / "CloudCoeff.nc"
        template = native_template_from_reference(source, model="crtm-cloud-v3")
        arrays = read_native_optical_arrays(source, model="crtm-cloud-v3")
        template["variables"]["ke_L_MW"]["dimensions"] = [
            "n_MW_Frequencies",
            "n_MW_Radii",
            "n_Temperatures",
        ]
        with self.assertRaisesRegex(ValueError, "dimension names/order"):
            write_native_optical_output(self.output / "wrong.nc", arrays, template)

    def test_rttov_multiple_species_and_unknown_model(self):
        template = rttov13_aerosol_output_template(
            2,
            {
                "dust": {"relative_humidity": [0], "confac": 100},
                "salt": {"relative_humidity": [0, 50], "confac": 200},
            },
            max_moments=32,
        )
        arrays = {}
        for name, spec in template["variables"].items():
            if "source" in spec:
                arrays[name] = np.zeros(spec["shape"])
        target = write_native_optical_output(self.output / "multi.H5", arrays, template)
        read = read_native_optical_arrays(target, model="rttov13")
        self.assertEqual(read["SCAER/SALT/ABS"].shape, (2, 1, 2))
        template = copy.deepcopy(template)
        template["model"] = "rttov14"
        with self.assertRaisesRegex(ValueError, "unknown native model"):
            write_native_optical_output(self.output / "wrong-version.H5", arrays, template)


if __name__ == "__main__":
    unittest.main()
