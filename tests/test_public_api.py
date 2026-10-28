"""Scientific equivalence and dispatch contracts for the consolidated API."""

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import zju_scatt_interface as scatt
import zju_scatt_interface.api as _domain_api
import zju_scatt_interface.api as api
import zju_scatt_interface.bulk.ensemble as _domain_bulk_ensemble
import zju_scatt_interface.bulk.integration as _domain_bulk_integration
import zju_scatt_interface.bulk.workflow as _domain_bulk_workflow
import zju_scatt_interface.config.scheme as _domain_config_scheme
import zju_scatt_interface.io.canonical as _domain_io_canonical
import zju_scatt_interface.io.products as _domain_io_products
import zju_scatt_interface.optics.models as _domain_optics_models
import zju_scatt_interface.psd.models as _domain_psd_models
import zju_scatt_interface.sources.planning as _domain_sources_planning
from tests.test_bulk_pipeline import create_source
from tests.test_phase8_output import calculation, scheme_result
from zju_scatt_interface.bulk.grid import BulkDimension, MultiBulkScheme, SingleBulkScheme
from zju_scatt_interface.bulk.tables import BulkTableResult
from zju_scatt_interface.config.scheme import WaterCloudComponent
from zju_scatt_interface.optics.interpolation import OpticalNode, OpticalSourceRequest
from zju_scatt_interface.optics.loading import load_single
from zju_scatt_interface.sources.planning import WorkspaceLayout, build_dependency_queries


class PublicApiTests(unittest.TestCase):
    def setUp(self):
        self.session = patch.dict(os.environ, {"ZJU_SCATT_SESSION": "public-api-regression"})
        self.session.start()
        self.addCleanup(self.session.stop)

    def test_interpolate_and_integrate_preserve_numerical_results(self):
        nodes = [
            OpticalNode(
                {"wavelength": wavelength},
                _domain_optics_models.SingleParticleOptics(
                    sizes=[1.0, 2.0, 3.0],
                    extinction_cross_section=[ext] * 3,
                    scattering_cross_section=[ext / 2] * 3,
                    size_unit="um",
                    cross_section_unit="m2",
                ),
            )
            for wavelength, ext in ((1.0, 4.0), (3.0, 16.0))
        ]
        result = _domain_api.interpolate(
            nodes, {"wavelength": 2.0}, particle_type="sphere_water_cloud"
        )
        self.assertAlmostEqual(result.optics.extinction_cross_section[0], 8.0)
        psd = _domain_psd_models.SizeDistribution([1.0, 2.0, 3.0], [1.0, 2.0, 1.0])
        actual, report = _domain_bulk_integration.integrate(result.optics, psd)
        # Four particles per cm^3, each with Cext=8 and Csca=4 m^2.
        self.assertAlmostEqual(actual.extinction_coefficient, 32e6)
        self.assertAlmostEqual(actual.scattering_coefficient, 16e6)
        self.assertAlmostEqual(actual.absorption_coefficient, 16e6)
        self.assertAlmostEqual(actual.single_scattering_albedo, 0.5)
        self.assertAlmostEqual(actual.number_concentration, 4.0)
        self.assertEqual(report.truncation_policy, "error")
        combined = _domain_bulk_ensemble.combine([actual, actual], [0.25, 0.75])
        self.assertAlmostEqual(combined.extinction_coefficient, actual.extinction_coefficient)
        for sources in ([], [nodes[0], OpticalSourceRequest("missing.nc", {})]):
            with self.assertRaises(TypeError):
                _domain_api.interpolate(sources, {}, particle_type="sphere_water_cloud")

    def test_loaded_sources_and_builds_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / f"L1_sphere_water_cloud_wl_{w:.3f}_um_ref_1.3_0.nc" for w in (0.5, 0.7)]
            for path, wavelength in zip(paths, (0.5, 0.7)):
                create_source(path, wavelength=wavelength, phase=True)
            requests = [
                OpticalSourceRequest(path, {"wavelength": w}, include_phase_matrix=True)
                for path, w in zip(paths, (0.5, 0.7))
            ]
            interpolated = _domain_api.interpolate(
                requests, {"wavelength": 0.6}, particle_type="sphere_water_cloud"
            )
            self.assertEqual(interpolated.provenance.method, "multilinear")
            component = WaterCloudComponent("cloud", size=[0.1, 1.0, 10.0], dndr=[1.0, 8.0, 1.0])
            scheme = _domain_config_scheme.Scheme("api_scheme", (0.5, 0.6), (component,))
            self.assertTrue(_domain_api.validate(scheme))
            dataset = _domain_api.build(
                scheme, source_paths=paths, truncation_policy="truncate", include_phase_matrix=True
            )
            population = _domain_bulk_workflow.compute_population(
                "sphere_water_cloud",
                paths,
                component.size_distribution,
                wavelength=0.6,
                truncation_policy="truncate",
                include_phase_matrix=True,
            )
            for name in (
                "extinction_coefficient",
                "scattering_coefficient",
                "absorption_coefficient",
                "single_scattering_albedo",
                "asymmetry_factor",
                "number_concentration",
            ):
                self.assertAlmostEqual(
                    getattr(dataset.components["cloud"][1].bulk, name),
                    getattr(population.bulk, name),
                )
            self.assertIsInstance(load_single(paths[0]), _domain_optics_models.SingleParticleOptics)
            grid_scheme = SingleBulkScheme(
                "cloud_grid", component, (BulkDimension("wavelength", (0.5, 0.6), unit="um"),)
            )
            grid = _domain_api.build(grid_scheme, source_paths=paths, truncation_policy="truncate")
            multi = _domain_api.build(
                MultiBulkScheme("multi", (grid_scheme,)),
                source_paths=paths,
                truncation_policy="truncate",
            )
            for name, product in (
                ("dataset", dataset),
                ("population", population),
                ("grid", grid),
                ("multi", multi),
            ):
                for suffix in ("nc", "h5"):
                    path = _domain_io_products.write(product, root / f"{name}.{suffix}")
                    self.assertTrue(_domain_api.validate(path).passed, path)
                    self.assertTrue(_domain_io_canonical.read(path)["components"])

    def test_writer_dispatch_preserves_members_phase_and_spectra(self):
        result = calculation(0.67)
        products = [
            result,
            [result, calculation(1.0)],
            scheme_result(),
            BulkTableResult(scheme_result(), {"source_manifests": {"source": "manifest.json"}}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i, product in enumerate(products):
                for suffix in ("nc", "hdf5"):
                    path = _domain_io_products.write(product, root / f"product_{i}.{suffix}")
                    content = _domain_io_canonical.read(path)
                    self.assertTrue(_domain_api.validate(path).passed)
                    data = next(iter(content["components"].values()))["datasets"]
                    self.assertIn("p11", data)
                    self.assertIn("shape_weight", data)
                    self.assertIn("psd_dndr", data)
                    self.assertEqual(data["wavelength"]["data"][0], 0.67)
            for product, options in (
                (result.bulk, {"wavelength_um": 0.67}),
                ([result.bulk, result.bulk], {"wavelengths_um": [0.67, 1.0]}),
            ):
                path = _domain_io_products.write(product, root / "bare.h5", **options)
                self.assertTrue(_domain_io_canonical.read(path)["components"])
            explicit = _domain_io_products.write(result, root / "explicit.bin", format="hdf5")
            self.assertTrue(_domain_io_canonical.read(explicit, format="hdf5")["components"])
            invalid = [
                ([], {}),
                ([result, result.bulk], {}),
                (object(), {}),
                (result.bulk, {}),
                (result, {"wavelength_um": 0.67}),
                ([result.bulk], {"wavelengths_um": [0.5, 0.7]}),
            ]
            for product, options in invalid:
                target = root / "invalid.nc"
                with self.assertRaises((TypeError, ValueError)):
                    _domain_io_products.write(product, target, **options)
                self.assertFalse(target.exists())

    def test_plan_is_selection_only_and_build_passes_plan(self):
        scheme = _domain_config_scheme.Scheme(
            "planned", (0.55,), (WaterCloudComponent("cloud", size=[1.0, 2.0], dndr=[1.0, 1.0]),)
        )
        with patch(
            "zju_scatt_interface.extensions.builtins.prepare_scheme_dependencies"
        ) as prepare:
            ready = Mock(
                spec=_domain_sources_planning.DependencyPlan,
                complete=True,
                offline=True,
                scheme_name=scheme.name,
                queries=build_dependency_queries(scheme),
            )
            ready.workspace = Mock(root=Path("workspace").resolve())
            prepare.return_value = ready
            dependency = _domain_api.plan(scheme, workspace="workspace", offline=True)
            prepare.assert_called_once_with(
                scheme, download=False, workspace="workspace", offline=True
            )
            with patch("zju_scatt_interface.extensions.builtins.build_dataset") as builder:
                _domain_api.build(scheme, plan=dependency, offline=True)
                builder.assert_called_once_with(
                    scheme, dependency_plan=dependency, workspace=ready.workspace.root, offline=True
                )
            with self.assertRaises(ValueError):
                _domain_api.plan(scheme, download=True)
            self.assertEqual(prepare.call_count, 1)

    def test_incomplete_plan_refresh_uses_same_workspace_and_offline_policy(self):
        scheme = _domain_config_scheme.Scheme(
            "planned", (0.55,), (WaterCloudComponent("cloud", size=[1.0, 2.0], dndr=[1.0, 1.0]),)
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = WorkspaceLayout.create(directory, "bulk.nc")
            pending = _domain_sources_planning.DependencyPlan(
                "1.0",
                scheme.name,
                "key",
                True,
                workspace,
                workspace.manifest_dir / "sources.json",
                build_dependency_queries(scheme),
                (),
                (),
            )
            with (
                patch(
                    "zju_scatt_interface.extensions.builtins.prepare_scheme_dependencies"
                ) as prepare,
                patch("zju_scatt_interface.extensions.builtins.build_dataset") as builder,
            ):
                _domain_api.build(scheme, plan=pending)
                prepare.assert_called_once_with(scheme, workspace=workspace.root, offline=True)
                builder.assert_called_once_with(
                    scheme,
                    dependency_plan=prepare.return_value,
                    workspace=workspace.root,
                    offline=True,
                )
            with patch(
                "zju_scatt_interface.extensions.builtins.prepare_scheme_dependencies"
            ) as prepare:
                with self.assertRaises(ValueError):
                    _domain_api.build(
                        _domain_config_scheme.Scheme(
                            "other", scheme.wavelengths_um, scheme.particles
                        ),
                        plan=pending,
                    )
                with self.assertRaises(ValueError):
                    _domain_api.build(scheme, plan=pending, source_paths="sources")
                prepare.assert_not_called()

    def test_plot_dispatch_is_explicit_for_paths(self):
        with patch("zju_scatt_interface.plotting.bulk.plot_bulk_optics") as bulk_plot:
            result = calculation(0.67)
            _domain_api.plot(result, output_dir="figures")
            bulk_plot.assert_called_once_with(result.bulk, output_dir="figures")
            with self.assertRaises(ValueError):
                _domain_api.plot("missing.nc")
            with self.assertRaises(TypeError):
                _domain_api.plot(result, kind="single")


if __name__ == "__main__":
    unittest.main()
