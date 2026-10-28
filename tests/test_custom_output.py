"""Custom layout export: species axes, checked units and grouped NC/HDF parity."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
from netCDF4 import Dataset

from zju_scatt_interface.io.custom import export_bulk_optics


def fixture():
    def record(data,dimensions,units="1"):
        return {"data":data,"dimensions":dimensions,"units":units}
    return {"datasets":{},"components":{
        "super_spheroid":{"attributes":{"particle_type":"super_spheroid"},"datasets":{
            "wavelength":record([10.,11.],["wavelength"],"um"),
            "relative_humidity":record([0.,.5,.99],["relative_humidity"]),
            "beta_ext":record([[1.,2.,3.],[4.,5.,6.]],["wavelength","relative_humidity"],"m^-1"),
            "ssa":record([[.8]*3]*2,["wavelength","relative_humidity"]),
        }},
        "encapsulated_fractal_aggregates_black_carbon":{"attributes":{},"datasets":{
            "wavelength":record([10.,11.],["wavelength"],"um"),
            "beta_ext":record([7.,8.],["wavelength"],"m^-1"),
            "ssa":record([.7,.9],["wavelength"]),
        }}}}


def specification(fmt="netcdf4"):
    return {"format":fmt,"filename":"optics.nc" if fmt=="netcdf4" else "optics.h5",
        "species_names":{"dust":"DU","black_carbon":"BC"},"group":"Optics/{species}",
        "dimensions":["relative_humidity","wavelength"],
        "coordinates":{"relative_humidity":{"name":"RH","units":"%"},
                       "wavelength":{"name":"lambda","units":"nm"}},
        "variables":{"extinction":{"source":"beta_ext","units":"km^-1","dtype":"float32"},
                     "albedo":{"source":"ssa"}},"attributes":{"title":"User optics"}}


class CustomOutputTests(unittest.TestCase):
    def test_result_object_and_multidimensional_grid_use_the_same_exporter(self):
        from tests.test_phase8_output import calculation, scheme_result
        from zju_scatt_interface.bulk.grid import BulkDimension, BulkGrid
        from zju_scatt_interface.io.canonical import _write_dataset as _write_dataset
        with tempfile.TemporaryDirectory() as directory:
            spec={"format":"nc","filename":"result.nc","variables":{"ext":{"source":"beta_ext"}}}
            export_bulk_optics(SimpleNamespace(scheme=scheme_result()),spec,output_dir=directory)
            grid=BulkGrid("ice_grid","super_spheroid_ice",(
                BulkDimension("wavelength",(.67,1.),unit="um"),
                BulkDimension("temperature",(220.,270.),unit="K")),(
                calculation(.67,1.,temperature=220.),calculation(.67,2.,temperature=270.),
                calculation(1.,3.,temperature=220.),calculation(1.,4.,temperature=270.)))
            spec.update(filename="grid.nc",dimensions=["temperature","wavelength"])
            export_bulk_optics(grid,spec,output_dir=directory)
            with Dataset(Path(directory)/"grid.nc") as nc:
                np.testing.assert_array_equal(nc["ice_grid/ext"][:],[[10,30],[20,40]])
                self.assertEqual(nc["ice_grid/ext"].dimensions,("temperature","wavelength"))
            source=Path(directory)/"canonical.nc"
            _write_dataset(source,scheme_result(), format='netcdf4')
            spec.update(filename=str(source),dimensions=[])
            with self.assertRaisesRegex(ValueError,"canonical source"):
                export_bulk_optics(source,spec,overwrite=True)

    def test_grouped_hdf_and_nc_units_order_and_missing_axes(self):
        data=fixture(); original=copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as directory:
            result=export_bulk_optics(data,{"outputs":[specification(),specification("hdf5")]},output_dir=directory)
            self.assertEqual(data,original)
            self.assertEqual(len(result["outputs"]),2)
            with Dataset(Path(directory)/"optics.nc") as nc,h5py.File(Path(directory)/"optics.h5") as h:
                e=nc["Optics/DU/extinction"]
                self.assertEqual(e.dimensions,("RH","lambda"))
                self.assertEqual(e.dtype,np.dtype("float32"))
                np.testing.assert_array_equal(e[:],np.array([[1,4],[2,5],[3,6]])*1000)
                np.testing.assert_array_equal(nc["Optics/DU/RH"][:],[0,50,99])
                np.testing.assert_allclose(nc["Optics/DU/lambda"][:],[10000,11000])
                self.assertEqual(nc["Optics/BC/extinction"].dimensions,("lambda",))
                self.assertNotIn("RH",nc["Optics/BC"].variables)
                for group in ("DU","BC"):
                    for variable in nc[f"Optics/{group}"].variables:
                        key=f"Optics/{group}/{variable}"
                        np.testing.assert_array_equal(nc[key][:],h[key][:])
                        self.assertEqual(nc[key].units,h[key].attrs["units"])

    def test_invalid_conversion_cast_and_axis_fail_before_writing(self):
        for mutation,error in ((lambda s:s["variables"]["extinction"].update(units="m2 kg-1"),"Unsupported unit"),
            (lambda s:s["variables"]["extinction"].update(dimensions=["wavelength"]),"permutation"),
            (lambda s:s["coordinates"].update(wavelength={"name":"../bad"}),"Invalid portable"),
            (lambda s:s.update(unknown=True),"Unknown custom")):
            with tempfile.TemporaryDirectory() as directory:
                spec=specification(); mutation(spec)
                with self.assertRaisesRegex(ValueError,error):
                    export_bulk_optics(fixture(),spec,output_dir=directory)
                self.assertFalse((Path(directory)/"optics.nc").exists())
        with tempfile.TemporaryDirectory() as directory:
            spec=specification(); spec["variables"]["albedo"]={"source":"ssa","dtype":"int32"}
            with self.assertRaisesRegex(ValueError,"represented"):
                export_bulk_optics(fixture(),spec,output_dir=directory)

    def test_json_and_python_paths_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); config=root/"format.json"
            config.write_text(json.dumps(specification()))
            result=export_bulk_optics(fixture(),config)
            self.assertEqual(Path(result["outputs"][0]),root/"optics.nc")
            with self.assertRaises(FileExistsError):
                export_bulk_optics(fixture(),config)
            config=root/"format.py"; config.write_text("output = "+repr(specification("hdf5")))
            export_bulk_optics(fixture(),config)
            export_bulk_optics(fixture(),config,overwrite=True)

    def test_all_outputs_preflight_no_partial_write_and_coordinate_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            bad=specification("hdf5"); bad["variables"]["albedo"]={"source":"missing"}
            with self.assertRaisesRegex(ValueError,"Missing optical"):
                export_bulk_optics(fixture(),{"outputs":[specification(),bad]},output_dir=directory)
            self.assertFalse((Path(directory)/"optics.nc").exists())
            data=fixture(); data["components"]["super_spheroid"]["datasets"]["wavelength"]["data"]=[10]
            with self.assertRaisesRegex(ValueError,"length mismatch"):
                export_bulk_optics(data,specification(),output_dir=directory)

    def test_flat_layout_and_name_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            spec=specification(); spec.update(group="",coordinates={})
            spec["variables"]={"{species}_ext":{"source":"beta_ext"}}
            export_bulk_optics(fixture(),spec,output_dir=directory)
            with Dataset(Path(directory)/"optics.nc") as nc:
                self.assertIn("DU_ext",nc.variables); self.assertIn("BC_ext",nc.variables)
            spec["variables"]={"ext":{"source":"beta_ext"}}
            with self.assertRaisesRegex(ValueError,"Conflicting output"):
                export_bulk_optics(fixture(),spec,output_dir=directory,overwrite=True)


if __name__=="__main__":
    unittest.main()
