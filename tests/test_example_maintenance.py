"""Current report compatibility for the opt-in cached-output maintenance examples."""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.errors as _domain_errors
from tests.test_native_retrieval import native_fixture
from zju_scatt_interface.optics.refractive_index import ResolvedGridRefractiveIndex
from zju_scatt_interface.optics.retrieval.ice import write_products
from zju_scatt_interface.optics.retrieval.workflow import interpolate_downloaded_particle_series
from zju_scatt_interface.sources.selection import select_shape_grid_sources

LOCAL = Path(__file__).resolve().parents[2] / "test_zju_scatt/user_test_local"


def load_script(name):
    with patch.object(sys, "path", [str(LOCAL), *sys.path]):
        spec = importlib.util.spec_from_file_location(name, LOCAL / name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


@unittest.skipUnless(LOCAL.is_dir(), "Workspace examples not present")
class ExampleMaintenanceTests(unittest.TestCase):
    def run_audit(self, report, root):
        audit = load_script("07_audit_native_outputs.py")
        with (
            patch.object(
                sys, "argv", ["audit", "--reports", str(report), "--output-dir", str(root)]
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            audit.main()
        return json.loads((root / "native_schema_audit.json").read_text())

    def test_dimensionless_ri_report_regenerates_and_audits_without_wavelength(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = (
                root
                / "L1_super_spheroid_n_2.000_asp_1.000_wl_nan_ref_1.500e+00_5.000e-03_v1.0_20260409.nc"
            )
            native_fixture(path, None, 2)
            obj = _domain_access_models.RemoteObject("Single_opt/super_spheroid/" + path.name, path.stat().st_size)
            point = ResolvedGridRefractiveIndex(
                "super_spheroid",
                None,
                {"refractive_index_real": 1.5, "refractive_index_imaginary": 0.005},
                "explicit_refractive_index",
                {},
            )
            _, resolutions, _ = select_shape_grid_sources(
                [obj], "super_spheroid", [point], [{"roundness": 2.0, "aspect_ratio": 1.0}]
            )
            processing = _domain_access_models.WavelengthProcessing(refractive_index_resolutions=resolutions)
            products = interpolate_downloaded_particle_series(
                [(obj, path)], [None], processing, root / "interpolated"
            )
            result = _domain_access_models.RetrievalResult(
                [obj],
                _domain_access_models.ScanStats(),
                processing,
                download_results=[_domain_access_models.DownloadResult(obj, path, "skipped")],
                interpolated_products=products,
            )
            report = result.write_report(root / "retrieval_report.json")
            with contextlib.redirect_stdout(io.StringIO()):
                load_script("06_regenerate_native_outputs.py").regenerate(report, overwrite=True)
            audited = self.run_audit(report, root / "audit")
            self.assertEqual(audited["verified_native_products"], 1)
            self.assertIsNone(audited["files"][0]["target_wavelength_um"])

    def test_ice_boundary_nan_report_regenerates_and_is_recognized_by_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = []
            for temperature in (160, 270):
                for wavelength in (1.5, 2.0):
                    path = (
                        root
                        / f"L1.5_super_spheroid_ice_n_2.000_asp_1.000_wl_{wavelength:.3f}_um_ref_1.3_0.01_t_{temperature}k_v1.0_20260403.nc"
                    )
                    native_fixture(path, wavelength, 2)
                    obj = _domain_access_models.RemoteObject(
                        "Single_opt/super_spheroid_ice/" + path.name, path.stat().st_size
                    )
                    sources.append((obj, path))
            processing = _domain_access_models.WavelengthProcessing(
                target_wavelengths_um=(1.6,), target_temperatures_k=(110,)
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                products = write_products(sources, [1.6], [110], root / "interpolated")
            result = _domain_access_models.RetrievalResult(
                [o for o, _ in sources],
                _domain_access_models.ScanStats(),
                processing,
                download_results=[_domain_access_models.DownloadResult(o, p, "skipped") for o, p in sources],
                interpolated_products=products,
            )
            report = result.write_report(root / "retrieval_report.json")
            with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
                warnings.simplefilter("ignore")
                load_script("06_regenerate_native_outputs.py").regenerate(report, overwrite=True)
            audited = self.run_audit(report, root / "audit")
            self.assertTrue(audited["files"][0]["declared_out_of_bounds"])
            self.assertEqual(audited["files"][0]["valid_cext_cells"], 0)

    def test_target_wavelength_example_enforces_download_completion(self):
        project = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "target_example", project / "examples/example_02_target_wavelength_retrieval.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = _domain_access_models.RetrievalResult(
            [], _domain_access_models.ScanStats(), _domain_access_models.WavelengthProcessing(), status_code=2
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(module, 'retrieve_sources', return_value=result),
            patch.object(module, "initialize_data_directory"),
        ):
            with self.assertRaisesRegex(_domain_errors.ScattError, "status 2"):
                module.run_example(Path(directory))
