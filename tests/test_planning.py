import hashlib
import json
import tempfile
import unittest

import zju_scatt_interface.access.download as _domain_access_download
import zju_scatt_interface.access.endpoints as _domain_access_endpoints
import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.access.requests as _domain_access_requests
from zju_scatt_interface.config.scheme import Scheme
from zju_scatt_interface.sources.planning import (
    WorkspaceLayout,
    build_dependency_queries,
    prepare_scheme_dependencies,
)


def _scheme(particle_type: str = "water_cloud") -> Scheme:
    return Scheme.from_mapping(
        {
            "name": "phase3_demo",
            "wavelength_unit": "um",
            "wavelengths": [0.55, 0.67],
            "particles": [
                {
                    "name": "cloud",
                    "particle_type": particle_type,
                    "size_distribution": {
                        "size": [1.0],
                        "dndr": [1.0],
                    },
                    "refractive_index": {"mode": "database"},
                }
            ],
            "output": "outputs/phase3_demo.nc",
        }
    )


class DependencyQueryTests(unittest.TestCase):
    def test_grid_planner_delegates_native_brackets_to_retrieval(self):
        from types import SimpleNamespace

        from zju_scatt_interface.config.particles import get_particle_profile
        from zju_scatt_interface.sources.adapters.planning import _retrieval_shapes

        component = SimpleNamespace(
            shape_parameters={},
            shape_ensemble=(
                {"parameters": {"n": 2.7, "asp": 1.5}, "weight": 0.5},
                {"parameters": {"n": 2.5, "asp": 1.3}, "weight": 0.5},
            ),
        )
        self.assertEqual(
            _retrieval_shapes(get_particle_profile("dust"), component),
            [{"roundness": 2.7, "aspect_ratio": 1.5}, {"roundness": 2.5, "aspect_ratio": 1.3}],
        )

    def test_planner_queries_use_unified_shapes_and_keep_internal_axes_out(self):
        config = Scheme.from_mapping(
            {
                "name": "ice_shapes",
                "wavelengths": [1.6],
                "particles": [
                    {
                        "name": "ice",
                        "particle_type": "ice",
                        "size_distribution": {"size": [1], "dndr": [1]},
                        "shape_parameters": {"roundness": 2, "aspect_ratio": 1},
                        "refractive_index": {"mode": "database_temperature", "temperature_k": 250},
                    }
                ],
            }
        )
        query = build_dependency_queries(config)[0]
        self.assertEqual(
            query.retrieval_parameters["shapes"], [{"roundness": 2, "aspect_ratio": 1}]
        )
        self.assertEqual(query.retrieval_parameters["target_temperatures"], [250])
        self.assertNotIn("shape_targets", query.retrieval_parameters)
        self.assertNotIn("shape_ranges", query.retrieval_parameters)
        _domain_access_requests.make_retrieval_args(**query.retrieval_parameters)

    def test_planner_brackets_non_native_geometry_for_computation(self):
        from types import SimpleNamespace

        from zju_scatt_interface.config.particles import get_particle_profile
        from zju_scatt_interface.sources.adapters.planning import _retrieval_shapes

        component = SimpleNamespace(shape_parameters={"n": 2.1, "asp": 1.1}, shape_ensemble=())
        shapes = _retrieval_shapes(get_particle_profile("ice"), component)
        self.assertEqual(shapes, [{"roundness": (2, 2.25), "aspect_ratio": (1, 1.25)}])

    def test_planner_preserves_ensemble_pairs(self):
        from types import SimpleNamespace

        from zju_scatt_interface.config.particles import get_particle_profile
        from zju_scatt_interface.sources.adapters.planning import _retrieval_shapes

        component = SimpleNamespace(
            shape_parameters={},
            shape_ensemble=(
                {"parameters": {"n": 2, "asp": 1}, "weight": 0.5},
                {"parameters": {"n": 3, "asp": 2}, "weight": 0.5},
            ),
        )
        self.assertEqual(
            _retrieval_shapes(get_particle_profile("ice"), component),
            [{"roundness": 2, "aspect_ratio": 1}, {"roundness": 3, "aspect_ratio": 2}],
        )

    def test_wavelength_profile_query_is_canonical_and_deterministic(self) -> None:
        alias_query = build_dependency_queries(_scheme("water_cloud"))[0]
        canonical_query = build_dependency_queries(_scheme("sphere_water_cloud"))[0]
        self.assertEqual(alias_query.particle_type, "sphere_water_cloud")
        self.assertEqual(
            alias_query.remote_source,
            "Single_opt/sphere_water_cloud/",
        )
        self.assertEqual(
            alias_query.retrieval_parameters["target_wavelengths"],
            [0.55, 0.67],
        )
        self.assertEqual(alias_query.cache_key, canonical_query.cache_key)

    def test_fixed_index_is_rejected_for_wavelength_database(self) -> None:
        config = _scheme()
        particle = config.particles[0]
        invalid = Scheme(
            name=config.name,
            wavelengths_um=config.wavelengths_um,
            particles=(
                type(particle)(
                    name=particle.name,
                    particle_type=particle.particle_type,
                    size_distribution=particle.size_distribution,
                    refractive_index={
                        "mode": "fixed",
                        "real": 1.33,
                        "imaginary": 0.0,
                    },
                ),
            ),
            output=config.output,
        )
        with self.assertRaisesRegex(ValueError, "must not supply a fixed"):
            build_dependency_queries(invalid)

    def test_black_carbon_query_records_all_native_indices(self) -> None:
        config = Scheme.from_mapping(
            {
                "name": "bc",
                "wavelengths": [0.55],
                "particles": [
                    {
                        "name": "bc",
                        "particle_type": "black_carbon",
                        "size_distribution": {
                            "size": [0.1],
                            "dndr": [1.0],
                        },
                        "shape_parameters": {"df": 1.8, "vf": 0.5},
                        "refractive_index": {
                            "mode": "fixed",
                            "black_carbon": {"real": 1.85, "imaginary": 0.55},
                            "hygroscopic": {"real": 1.4, "imaginary": 0.05},
                        },
                    }
                ],
            }
        )
        query = build_dependency_queries(config)[0]
        self.assertIn(
            "black_carbon_refractive_index_real",
            query.scientific_coordinates,
        )
        self.assertIn(
            "hygroscopic_refractive_index_imaginary",
            query.scientific_coordinates,
        )
        self.assertEqual(query.retrieval_parameters["target_wavelengths"], [0.55])
        self.assertEqual(
            query.retrieval_parameters["refractive_index_parameters"]["black_carbon"][
                "black_carbon_refractive_index_real"
            ],
            1.85,
        )


class SourcePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.obj = _domain_access_models.RemoteObject(
            key=(
                _domain_access_endpoints.ROOT_PREFIX
                + "Single_opt/sphere_water_cloud/data/L1_cloud_wl_0.550_um.nc"
            ),
            size=3,
            etag=hashlib.md5(b"abc").hexdigest(),
        )

    def _downloader(self, objects, layout):
        results = []
        for obj in objects:
            target = _domain_access_download.destination_for(obj, layout.cache_dir, flat=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"abc")
            results.append(_domain_access_models.DownloadResult(obj, target, "downloaded"))
        return results

    def test_reuse_directory_checks_hash_and_preserves_original(self):
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "previous"
            previous.mkdir()
            original = previous / self.obj.name
            original.write_bytes(b"abc")

            def forbidden(*args):
                self.fail("A hash-matched earlier download should not be downloaded again")

            plan = prepare_scheme_dependencies(
                _scheme(),
                workspace=root / "new",
                validate_schema=False,
                searcher=lambda query: [self.obj],
                downloader=forbidden,
                reuse_dirs=[previous],
            )
            self.assertTrue(plan.complete)
            self.assertEqual(original.read_bytes(), b"abc")
            self.assertEqual(plan.sources[0].cache_path.read_bytes(), b"abc")
            original.write_bytes(b"bad")  # Same filename and size, different content.
            rejected = prepare_scheme_dependencies(
                _scheme(),
                workspace=root / "other",
                validate_schema=False,
                searcher=lambda query: [self.obj],
                download=False,
                reuse_dirs=[previous],
            )
            self.assertFalse(rejected.complete)

    def test_online_plan_downloads_validates_manifests_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def downloader(objects, layout):
                calls.append(tuple(obj.key for obj in objects))
                return self._downloader(objects, layout)

            first = prepare_scheme_dependencies(
                _scheme(),
                workspace=directory,
                validate_schema=False,
                searcher=lambda _query: [self.obj],
                downloader=downloader,
            )
            second = prepare_scheme_dependencies(
                _scheme(),
                workspace=directory,
                validate_schema=False,
                searcher=lambda _query: [self.obj],
                downloader=downloader,
            )
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))

        self.assertTrue(first.complete)
        self.assertTrue(second.complete)
        self.assertEqual(len(calls), 1)
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["summary"]["ready_count"], 1)
        self.assertEqual(
            manifest["sources"][0]["local_sha256"],
            hashlib.sha256(b"abc").hexdigest(),
        )

    def test_offline_mode_reuses_manifest_and_reports_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            online = prepare_scheme_dependencies(
                _scheme(),
                workspace=directory,
                validate_schema=False,
                searcher=lambda _query: [self.obj],
                downloader=self._downloader,
            )
            offline = prepare_scheme_dependencies(
                _scheme(),
                workspace=directory,
                offline=True,
                validate_schema=False,
            )
            self.assertTrue(offline.complete)
            online.sources[0].cache_path.write_bytes(b"changed")
            damaged = prepare_scheme_dependencies(
                _scheme(),
                workspace=directory,
                offline=True,
                validate_schema=False,
            )
        self.assertFalse(damaged.complete)
        self.assertEqual(damaged.sources[0].status, "invalid_size")
        self.assertIn("reconnect and rerun", damaged.issues[-1].action)

    def test_offline_without_manifest_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = prepare_scheme_dependencies(
                _scheme(),
                workspace=directory,
                offline=True,
                validate_schema=False,
            )
        self.assertFalse(plan.complete)
        self.assertIn("without --offline", plan.issues[0].action)

    def test_workspace_creates_cache_work_manifest_and_output_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            layout = WorkspaceLayout.create(directory, "outputs/result.nc")
            self.assertTrue(layout.cache_dir.is_dir())
            self.assertTrue(layout.work_dir.is_dir())
            self.assertTrue(layout.manifest_dir.is_dir())
            self.assertTrue(layout.output_file.parent.is_dir())

    def test_default_schema_validation_accepts_valid_l1_file(self) -> None:
        try:
            from netCDF4 import Dataset
        except ImportError:
            self.skipTest("netCDF4 is not installed")

        obj = _domain_access_models.RemoteObject(
            key=(
                _domain_access_endpoints.ROOT_PREFIX
                + "Single_opt/sphere_water_cloud/data/L1_cloud_wl_0.550_um.nc"
            )
        )

        def downloader(objects, layout):
            results = []
            for remote in objects:
                target = _domain_access_download.destination_for(
                    remote, layout.cache_dir, flat=False
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                with Dataset(target, "w") as dataset:
                    dataset.dataset_name = "sphere_water_cloud"
                    dataset.data_version = "v1.0"
                    dataset.createDimension("size", 1)
                    dataset.createDimension("angle", 1)
                    dataset.createVariable("xsize_veq", "f8", ("size",))[:] = [1.0]
                    dataset.createVariable("sca_angle", "f8", ("angle",))[:] = [0.0]
                    for name in ("cext", "ssa", "g"):
                        dataset.createVariable(name, "f8", ("size",))[:] = [1.0]
                    for name in ("p11", "p12", "p22", "p33", "p43", "p44"):
                        dataset.createVariable(
                            name,
                            "f8",
                            ("size", "angle"),
                        )[:] = [[1.0]]
                results.append(_domain_access_models.DownloadResult(remote, target, "downloaded"))
            return results

        with tempfile.TemporaryDirectory() as directory:
            plan = prepare_scheme_dependencies(
                _scheme(),
                workspace=directory,
                searcher=lambda _query: [obj],
                downloader=downloader,
            )
        self.assertTrue(plan.complete)
        self.assertTrue(plan.sources[0].schema_validated)


if __name__ == "__main__":
    unittest.main()
