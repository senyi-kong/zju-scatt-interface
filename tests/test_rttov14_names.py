"""RTTOV14 group names and native name registry must stay consistent."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, chartostring
from test_rttov14_grid import item

from zju_scatt_interface.io.applications.rttov.lookup import (
    FIELDS,
    _write_grid,
    write_rttov14_lookup_slice,
)
from zju_scatt_interface.io.applications.rttov.names import rename_rttov14_species


class RTTOV14NameTests(unittest.TestCase):
    def test_fixed_population_rttov14_tables_are_supported(self):
        from zju_scatt_interface.io.applications.rttov.v14 import _write_table
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"fixed.nc"; target=Path(directory)/"named.nc"
            _write_table(source,"aertable",[10.,11.],{"dust":item([])},2)
            result=rename_rttov14_species(source,target,{"dust":"DU"})
            self.assertTrue(result["validation"]["passed"])
            with Dataset(target) as nc:
                self.assertIn("DU",nc["aertable"].groups)

    def test_renaming_preserves_values_and_allows_canonical_slice_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.nc"; target=Path(directory)/"named.nc"
            original=item([("relhum",np.array([0.,50.,99.])),("deff",np.array([.2,.4]))])
            _write_grid(source,"aertable",[10.,11.],{"dust":original},2,master=True)
            rename_rttov14_species(source,target,{"dust":"DU"})
            with Dataset(source) as a,Dataset(target) as b:
                self.assertIn("dust",a["aertable"].groups)
                self.assertEqual(list(b["aertable"].groups),["DU"])
                self.assertEqual([s.strip() for s in chartostring(b["aertable/names"][:])],["DU"])
                for field in FIELDS:
                    np.testing.assert_array_equal(a["aertable/dust"][field][:],b["aertable/DU"][field][:])
            sliced=Path(directory)/"slice.nc"
            write_rttov14_lookup_slice(target,sliced,aerosol_effective_radii_um={"dust":.2})
            with Dataset(sliced) as nc:
                self.assertIn("DU",nc["aertable"].groups)

    def test_duplicate_long_and_nonascii_names_fail_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.nc"; target=Path(directory)/"target.nc"
            _write_grid(source,"aertable",[10.,11.],{"dust":item([]),"black_carbon":item([])},2,master=True)
            for mapping in ({"dust":"BC","black_carbon":"BC"},{"dust":"D"*33},{"dust":"灰尘"}):
                with self.assertRaises(ValueError):
                    rename_rttov14_species(source,target,mapping)
                self.assertFalse(target.exists())
            with self.assertRaisesRegex(ValueError,"differ"):
                rename_rttov14_species(source,source,{"dust":"DU"})

    def test_name_swaps_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.nc"; target=Path(directory)/"target.nc"
            _write_grid(source,"aertable",[10.,11.],{"DU":item([]),"BC":item([])},2,master=True)
            rename_rttov14_species(source,target,{"DU":"BC","BC":"DU"})
            with Dataset(target) as nc:
                self.assertEqual([s.strip() for s in chartostring(nc["aertable/names"][:])],["BC","DU"])


if __name__=="__main__":
    unittest.main()
