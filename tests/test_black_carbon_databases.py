"""Independent BC families, RI schemes and boundary results."""

import math
import tempfile
import unittest
from pathlib import Path

import zju_scatt_interface.access.models as _domain_access_models
import zju_scatt_interface.sources.coordinates as _domain_sources_coordinates
from tests.test_adapters import create_l1
from zju_scatt_interface.bulk.workflow import compute_population
from zju_scatt_interface.config.scheme import Scheme
from zju_scatt_interface.psd.models import SizeDistribution
from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryWarning
from zju_scatt_interface.sources.adapters.registry import (
    interpolate_particle,
    resolve_particle_sources,
)
from zju_scatt_interface.sources.planning import build_dependency_queries


class BlackCarbonDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "encapsulated_fractal_aggregates_black_carbon"
        for scheme, n in (("v1.2.1", 3.0), ("v1.2.2", 3.5)):
            for wl in (10.0, 12.0):
                path = self.root / (
                    f"L1_encapsulated_fractal_aggregates_black_carbon_df_1.80_wl_{wl:.3f}_um_"
                    f"ref_bc_{n}_2.5_hygro_1.82_0.09_{scheme}_20260616.nc")
                create_l1(path, wavelength=wl, vf=[0.1, 0.5], df=True)
        path = self.root / (
            "L1_encapsulated_fractal_aggregates_black_carbon_df_1.80_wl_nan_"
            "ref_bc_1.65_0.55_hygro_1.2_0.001_v1.0_20260417.nc")
        create_l1(path, wavelength=None, vf=[0.1, 0.5], df=True)

    def parameters(self, **extra):
        return {"database_type": "wavelength", "ri_scheme": "v1.2.2",
                "df": 1.8, "vf": 0.5, **extra}

    def test_wavelength_interpolation_keeps_scheme_and_excludes_grid(self):
        resolution = resolve_particle_sources(
            "bc", self.root, wavelength=11, parameters=self.parameters())
        self.assertEqual(len(resolution.sources), 2)
        self.assertTrue(all("v1.2.2" in str(s.path) for s in resolution.sources))
        self.assertEqual(set(resolution.target_coordinates), {"wavelength", "df", "vf"})
        product = resolution.interpolate()
        self.assertEqual(product.provenance.method, "multilinear")
        self.assertTrue(all(math.isfinite(v) for v in product.optics.extinction_cross_section))

    def test_grid_default_excludes_both_wavelength_schemes(self):
        resolution = resolve_particle_sources("bc", self.root, wavelength=10,
            parameters={"df": 1.8, "vf": 0.5, "bc_mr": 1.65, "bc_mi": 0.55,
                        "hygro_mr": 1.2, "hygro_mi": 0.001})
        self.assertEqual(len(resolution.sources), 1)
        self.assertIn("wl_nan", str(resolution.sources[0].path))

    def test_boundary_warns_and_returns_nan(self):
        for wavelength, parameters in ((21, self.parameters()),
                                       (10, self.parameters(vf=0.8)),
                                       (10, self.parameters(df=2.4))):
            with self.subTest(wavelength=wavelength, parameters=parameters):
                with self.assertWarns(DatabaseBoundaryWarning):
                    product = interpolate_particle("bc", self.root, wavelength=wavelength,
                        parameters=parameters, target_size_um=[1, 2])
                self.assertEqual(product.provenance.method, "out_of_database_bounds")
                self.assertTrue(all(math.isnan(v) for v in product.optics.extinction_cross_section))

    def test_ir_index_outside_grid_returns_nan(self):
        with self.assertWarns(DatabaseBoundaryWarning):
            product = interpolate_particle("bc", self.root, wavelength=10,
                parameters={"df": 1.8, "vf": 0.5, "bc_mr": 3.5, "bc_mi": 2.5,
                            "hygro_mr": 1.82, "hygro_mi": 0.09}, target_size_um=[1])
        self.assertTrue(math.isnan(product.optics.extinction_cross_section[0]))

    def test_retrieval_keeps_both_wavelength_brackets_in_one_scheme(self):
        objects = [_domain_access_models.RemoteObject("Single_opt/" + self.root.name + "/" + p.name)
                   for p in self.root.glob("*.nc")]
        selected, details = _domain_sources_coordinates.select_for_target_wavelength(objects, [11],
            refractive_index_parameters={"bc": {"database_type": "wavelength",
                                                "ri_scheme": "v1.2.1"}})
        self.assertEqual(len(selected), 2)
        self.assertTrue(all("v1.2.1" in obj.key for obj in selected))
        self.assertTrue(details.interpolation_required)

    def test_bulk_boundary_is_nan_even_with_strict_qa(self):
        distribution = SizeDistribution(size=[1, 2], dndr=[1, 1])
        with self.assertWarns(DatabaseBoundaryWarning):
            result = compute_population("bc", self.root, distribution,
                wavelength=21, parameters=self.parameters())
        self.assertFalse(result.qa.passed)
        self.assertTrue(math.isnan(result.bulk.extinction_coefficient))

    def test_scheme_dependency_queries_preserve_database_and_scheme(self):
        queries = []
        for scheme in ("v1.2.1", "v1.2.2"):
            config = Scheme.from_mapping({
                "name": "bc", "wavelengths": [10, 12], "particles": [{
                    "name": "bc", "particle_type": "bc",
                    "size_distribution": {"size": [1, 2], "dndr": [1, 1]},
                    "shape_parameters": self.parameters(ri_scheme=scheme),
                    "refractive_index": {"mode": "database"}}]})
            query = build_dependency_queries(config)[0]
            queries.append(query)
            self.assertEqual(query.retrieval_parameters["refractive_index_parameters"]["black_carbon"],
                             {"database_type": "wavelength", "ri_scheme": scheme})
            self.assertNotIn("black_carbon_refractive_index_real", query.scientific_coordinates)
        self.assertNotEqual(queries[0].cache_key, queries[1].cache_key)

    def test_size_boundary_returns_nan_on_requested_size_grid(self):
        with self.assertWarns(DatabaseBoundaryWarning):
            product = interpolate_particle("bc", self.root, wavelength=10,
                parameters=self.parameters(), target_size_um=[100, 200])
        self.assertEqual(product.optics.sizes, [100, 200])
        self.assertTrue(all(math.isnan(v) for v in product.optics.extinction_cross_section))

    def test_cannot_interpolate_between_wavelength_ri_schemes(self):
        from zju_scatt_interface.optics.interpolation import (
            InterpolationError,
            OpticalNode,
            interpolate_nodes,
        )
        from zju_scatt_interface.optics.models import SingleParticleOptics

        nodes = [OpticalNode({"wavelength": 10, "df": 1.8, "vf": 0.5},
                            SingleParticleOptics(sizes=[1]), str(path))
                 for path in self.root.glob("*wl_10.000*")]
        with self.assertRaisesRegex(InterpolationError, "one RI scheme"):
            interpolate_nodes("bc", nodes,
                {"wavelength": 10, "df": 1.8, "vf": 0.5})


if __name__ == "__main__":
    unittest.main()
