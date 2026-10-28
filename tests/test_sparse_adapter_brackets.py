"""Regression: sparse RI axes must not be mistaken for out-of-bounds targets."""
import unittest
from pathlib import Path

from zju_scatt_interface.sources.adapters.base import _FileRecord, _retain_brackets
from zju_scatt_interface.sources.adapters.boundaries import DatabaseBoundaryError


class SparseBracketTests(unittest.TestCase):
    def records(self):
        return [_FileRecord(Path(f"source_{i}.nc"), {"mr": mr, "mi": mi})
                for i, (mr, mi) in enumerate(((1.65, 0.30), (1.65, 0.35), (1.7, 0.01), (1.7, 0.8)))]

    def test_later_axis_cannot_silently_remove_real_index_upper_support(self):
        target = {"mr": 1.6711052631578946, "mi": 0.33142105263157867}
        selected = _retain_brackets(self.records(), target, ("mr", "mi"))
        for axis in target:
            self.assertLessEqual(min(record.coordinates[axis] for record in selected), target[axis])
            self.assertGreaterEqual(max(record.coordinates[axis] for record in selected), target[axis])
        # This is the two-pass sequence used by ParticleAdapter.resolve().
        repeated = _retain_brackets(selected, target, ("mr", "mi"))
        self.assertEqual(selected, repeated)

    def test_true_database_boundary_remains_an_error(self):
        for target in ({"mr": 1.8, "mi": 0.33}, {"mr": 1.67, "mi": 0.9}):
            with self.assertRaises(DatabaseBoundaryError):
                _retain_brackets(self.records(), target, ("mr", "mi"))

    def test_complete_rectangle_keeps_original_corner_selection(self):
        records = [_FileRecord(Path(f"{a}_{b}.nc"), {"mr": a, "mi": b})
                   for a in (1.5, 1.6, 1.7) for b in (0.01, 0.1, 0.3)]
        selected = _retain_brackets(records, {"mr": 1.65, "mi": 0.2}, ("mr", "mi"))
        self.assertEqual({(r.coordinates["mr"], r.coordinates["mi"]) for r in selected},
                         {(1.6, 0.1), (1.6, 0.3), (1.7, 0.1), (1.7, 0.3)})

    def test_fixed_shape_does_not_inflate_sparse_interpolation_dimension(self):
        from zju_scatt_interface.optics.interpolation import OpticalNode, _select_neighbors
        target = {"mr": 1.66, "mi": 0.33, "n": 2.6, "asp": 0.5}
        nodes = [OpticalNode({"mr": mr, "mi": mi, "n": 2.6, "asp": 0.5}, None, str(i))
                 for i, (mr, mi) in enumerate(((1.65, 0.3), (1.65, 0.35), (1.7, 0.35)))]
        method, selected, weights, _, _ = _select_neighbors(tuple(target), target, nodes, sparse_power=2)
        self.assertEqual(method, "inverse_distance_sparse")
        self.assertEqual(len(selected), 3)
        self.assertAlmostEqual(sum(weights), 1)
        with self.assertRaises(ValueError):
            _select_neighbors(tuple(target), {**target, "n": 3.0}, nodes, sparse_power=2)


if __name__ == "__main__":
    unittest.main()
