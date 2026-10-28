"""Ensemble production exports retain shape targets, population and source provenance."""

import contextlib
import csv
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset

import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.manifests as _domain_access_manifests
import zju_scatt_interface.access.models as _domain_access_models
from tests.test_native_retrieval import native_fixture
from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.io.l2 import VARIABLES, write_l2_lognormal_members
from zju_scatt_interface.psd.analytical import lognormal_psd


def sources(root, shapes):
    paths = []
    for n, asp in shapes:
        path = (
            root
            / f"L1_super_spheroid_n_{n:.3f}_asp_{asp:.3f}_wl_nan_ref_1.500e+00_3.000e-03_v1.0_20260409.nc"
        )
        native_fixture(path, None, n + asp, grid=np.geomspace(0.01, 1000, 700))
        with Dataset(path, "a") as ds:
            ds.institution = "Synthetic ensemble source"
            ds["ssph_n"][...] = n
            ds["ssph_asp"][...] = asp
        paths.append(path)
    return paths


class EnsembleExportTests(unittest.TestCase):
    def test_shape_factory_rejects_mismatched_weights_and_defaults_to_equal(self):
        shapes = [{"n": 2, "asp": 1}, {"n": 2.8, "asp": 2}]
        self.assertEqual(
            [m.weight for m in WeightedShapeEnsemble.from_shapes(shapes).members], [0.5, 0.5]
        )
        with self.assertRaisesRegex(ValueError, "equal length"):
            WeightedShapeEnsemble.from_shapes(shapes, [1])

    def test_member_csv_and_l2_use_integrated_results_and_record_opaque_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = sources(root, [(2.0, 1.0), (2.8, 2.0)])
            psd = lognormal_psd(0.7, 1.8, 10, radius_range_um=(0.2, 5), normalization="renormalize")
            calculation = compute_population(
                "dust",
                paths,
                psd,
                wavelength=1.6,
                parameters={"mr": 1.5, "mi": 0.003},
                shape_ensemble=WeightedShapeEnsemble.from_shapes(
                    [{"n": 2, "asp": 1}, {"n": 2.8, "asp": 2}], [1, 3]
                ),
                include_phase_matrix=True,
                phase_normalization="unit_solid_angle",
                check_convergence=False,
            )
            # Source selection for exports must use provenance, not filenames.
            for index, member in enumerate(calculation.members):
                opaque = root / f"opaque_{index}.nc"
                shutil.copy2(member.interpolation_provenance["neighbors"][0]["source"], opaque)
                member.interpolation_provenance["neighbors"][0]["source"] = str(opaque)
            outputs = calculation.save(
                root / "out", size_distribution=psd, include_members=True, l2_lognormal=True
            )
            with Path(outputs["scalars_csv"]).open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 3)
            for index, member in enumerate(calculation.members):
                self.assertEqual(int(rows[index]["ensemble_member"]), index)
                self.assertAlmostEqual(float(rows[index]["number_fraction"]), member.weight)
                self.assertAlmostEqual(
                    float(rows[index]["extinction_coefficient_m-1"]),
                    member.bulk.extinction_coefficient,
                )
                self.assertAlmostEqual(
                    float(rows[index]["allocated_number_concentration_cm-3"]), 10 * member.weight
                )
                self.assertAlmostEqual(float(rows[index]["number_concentration_cm-3"]), 10)
                with Dataset(outputs["l2_members"][index]) as ds:
                    self.assertEqual(set(ds.variables), set(VARIABLES))
                    self.assertFalse(ds.groups)
                    self.assertAlmostEqual(
                        float(ds["beta_ext"][:]), member.bulk.extinction_coefficient / 10
                    )
                    self.assertIn(f"opaque_{index}.nc", ds.source_data)
            self.assertEqual(rows[-1]["population"], "ensemble_average")
            expected = sum(
                member.weight * member.bulk.extinction_coefficient for member in calculation.members
            )
            self.assertAlmostEqual(float(rows[-1]["extinction_coefficient_m-1"]), expected)
            self.assertEqual(len(outputs["l2_members"]), 2)  # No fictitious average-shape L2 file.
            report = json.loads(Path(outputs["report"]).read_text())
            self.assertEqual(len(report["member_scalar_rows"]), 2)
            self.assertIn("l2_members", report["outputs"])
            with Dataset(outputs["nc"]) as ds:
                np.testing.assert_array_equal(
                    ds.groups["bulk_optics"]["ensemble_member"][:], [0, 1]
                )

    def test_missing_provenance_cannot_fall_back_to_filename_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = sources(Path(directory), [(2.0, 1.0)])
            psd = lognormal_psd(0.7, 1.8, 10, radius_range_um=(0.2, 5))
            calculation = compute_population(
                "dust",
                paths,
                psd,
                wavelength=1.6,
                parameters={"mr": 1.5, "mi": 0.003},
                shape_ensemble=WeightedShapeEnsemble.from_shapes([{"n": 2, "asp": 1}]),
                check_convergence=False,
            )
            calculation.members[0].interpolation_provenance["neighbors"] = []
            with self.assertRaisesRegex(ValueError, "recorded in interpolation provenance"):
                write_l2_lognormal_members(Path(directory) / "out", calculation, psd)

    def test_both_short_examples_run_end_to_end_from_saved_catalogs(self):
        local = Path(__file__).resolve().parents[2] / "test_zju_scatt/user_test_local"
        if not local.is_dir():
            self.skipTest("Workspace examples not installed")
        jobs = [
            ("15_super_spheroid_lognormal_shape_average.py", [(2.8, 0.5), (2.8, 1.0), (2.8, 2.0)]),
            (
                "16_super_spheroid_interpolated_shapes_bulk.py",
                [(n, a) for n in (2.4, 2.6, 2.8) for a in (1.2, 1.4, 1.6, 1.8, 2.0)],
            ),
        ]
        for script, shapes in jobs:
            with self.subTest(script=script), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                paths = sources(root, shapes)
                objects = [
                    _domain_access_models.RemoteObject("Single_opt/super_spheroid/" + p.name, p.stat().st_size)
                    for p in paths
                ]
                by_key = {obj.key: path for obj, path in zip(objects, paths)}
                manifest = root / "catalog.jsonl"
                _domain_access_manifests.write_manifest(objects, manifest, "jsonl")

                def download(runtime, client, selected, stats):
                    return 0, [
                        _domain_access_models.DownloadResult(obj, by_key[obj.key], "skipped") for obj in selected
                    ]

                with patch.object(sys, "path", [str(local), *sys.path]):
                    spec = importlib.util.spec_from_file_location(script[:-3], local / script)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                with (
                    patch.object(_domain_access_download, 'download_selected_objects', side_effect=download),
                    patch.object(
                        sys,
                        "argv",
                        [script, "--manifest", str(manifest), "--output-dir", str(root / "out")],
                    ),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    module.main()
                report = json.loads((root / "out/summary.json").read_text())
                self.assertEqual(len(report["calculation"]["members"]), 3)
                self.assertAlmostEqual(report["bulk_optics"]["number_concentration_cm-3"], 10)
                with Dataset(root / "out/application_outputs/bulk_optics_10_cm3.nc") as ds:
                    component = next(iter(ds.groups.values()))
                    np.testing.assert_array_equal(component["ensemble_member"][:], [0, 1, 2])
                    expected = module.EXAMPLES["15" if script.startswith("15") else "16"]["shapes"]
                    np.testing.assert_allclose(
                        component["ssph_n"][0], [s["ssph_n"] for s in expected]
                    )
                    np.testing.assert_allclose(
                        component["ssph_asp"][0], [s["ssph_asp"] for s in expected]
                    )
                self.assertEqual(
                    len(report["outputs"].get("l2_members", [])),
                    3 if script.startswith("15") else 0,
                )
                self.assertNotIn("order_comparison", report)
