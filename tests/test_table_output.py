import json
import tempfile
import unittest
from pathlib import Path

from tests.test_phase8_output import calculation, scheme_result
from zju_scatt_interface.bulk.grid import BulkDimension, BulkGrid
from zju_scatt_interface.io.canonical import _write_dataset as _write_dataset
from zju_scatt_interface.io.tables import (
    OpticalTableFormat,
    bulk_output_records,
    load_optical_table_format,
    write_formatted_optical_output,
)


class OpticalTableOutputTests(unittest.TestCase):
    def test_custom_columns_units_and_per_component_filename(self):
        specification = {
            "name": "model_input_v1",
            "layout": "per_component",
            "delimiter": ",",
            "header_lines": ["format={format_name}", "records={record_count}"],
            "include_unit_header": True,
            "columns": [
                {"field": "component", "name": "species"},
                {"field": "wavelength_um", "format": ".3f", "unit": "um"},
                {
                    "field": "beta_ext",
                    "name": "extinction_km-1",
                    "format": ".4e",
                    "unit": "km^-1",
                    "scale": 1000.0,
                },
                {"field": "ssa", "format": ".5f", "unit": "1"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "optics.tbl"
            paths = write_formatted_optical_output(output, scheme_result(), specification)
            text = paths[0].read_text(encoding="utf-8")

        self.assertEqual(paths[0].name, "optics_ice.tbl")
        self.assertIn("# format=model_input_v1", text)
        self.assertIn("# species,wavelength_um,extinction_km-1,ssa", text)
        self.assertIn("# 1,um,km^-1,1", text)
        self.assertIn("ice,0.670,1.0000e+04,0.80000", text)

    def test_existing_netcdf_can_be_exported_without_recalculation(self):
        try:
            import netCDF4  # noqa: F401
        except ImportError:
            self.skipTest("netCDF4 is required")
        specification = {
            "name": "compact",
            "delimiter": "|",
            "columns": ["component", "wavelength_um", "beta_sca"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = _write_dataset(root / "canonical.nc", scheme_result(), format='netcdf4')
            table = write_formatted_optical_output(
                root / "model.dat", canonical, specification
            )
            text = table.read_text(encoding="utf-8")
        self.assertIn("ice|0.67|8.0", text)
        self.assertIn("ice|1.0|16.0", text)

    def test_multidimensional_coordinates_are_flattened_in_row_major_order(self):
        dimensions = (
            BulkDimension("wavelength", (0.67, 1.0), unit="um"),
            BulkDimension("temperature", (220.0, 270.0), unit="K"),
        )
        grid = BulkGrid(
            "ice_grid",
            "super_spheroid_ice",
            dimensions,
            (
                calculation(0.67, 1.0, temperature=220.0),
                calculation(0.67, 2.0, temperature=270.0),
                calculation(1.0, 3.0, temperature=220.0),
                calculation(1.0, 4.0, temperature=270.0),
            ),
        )
        records = bulk_output_records(grid)
        self.assertEqual(
            [(item["wavelength_um"], item["temperature"]) for item in records],
            [(0.67, 220.0), (0.67, 270.0), (1.0, 220.0), (1.0, 270.0)],
        )
        self.assertEqual([item["beta_ext"] for item in records], [10.0, 20.0, 30.0, 40.0])

    def test_phase_columns_expand_each_grid_point_over_scattering_angle(self):
        specification = OpticalTableFormat.from_mapping(
            {
                "name": "phase_long_table",
                "columns": [
                    {"field": "wavelength_um", "format": ".2f"},
                    {"field": "scattering_angle_degrees", "format": ".1f"},
                    {"field": "p11", "format": ".3f"},
                ],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            table = write_formatted_optical_output(
                Path(directory) / "phase.dat", scheme_result(), specification
            )
            rows = [
                line for line in table.read_text(encoding="utf-8").splitlines()
                if not line.startswith("#")
            ]
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0], "0.67 0.0 1.000")
        self.assertEqual(rows[-1], "1.00 180.0 1.000")

    def test_json_and_python_specs_are_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "format.json"
            json_path.write_text(
                json.dumps({"name": "json", "columns": ["wavelength_um"]}),
                encoding="utf-8",
            )
            python_path = root / "format.py"
            python_path.write_text(
                "def km(value, record):\n"
                "    return float(value) * 1000.0\n"
                "optical_table_format = {\n"
                "    'name': 'python',\n"
                "    'columns': [{'field': 'beta_ext', 'transform': km}],\n"
                "}\n",
                encoding="utf-8",
            )
            json_format = load_optical_table_format(json_path)
            python_format = load_optical_table_format(python_path)
        self.assertEqual(json_format.name, "json")
        self.assertEqual(python_format.name, "python")
        self.assertEqual(python_format.columns[0].transform(2.0, {}), 2000.0)

    def test_row_template_uses_transformed_output_column_names(self):
        specification = {
            "name": "fixed_width",
            "include_column_header": False,
            "row_template": "{wl:8.3f}{ext:14.5e}",
            "columns": [
                {"field": "wavelength_um", "name": "wl"},
                {"field": "beta_ext", "name": "ext", "scale": 1000.0},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            table = write_formatted_optical_output(
                Path(directory) / "fixed.dat", scheme_result(), specification
            )
            rows = table.read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0], "   0.670   1.00000e+04")


if __name__ == "__main__":
    unittest.main()
