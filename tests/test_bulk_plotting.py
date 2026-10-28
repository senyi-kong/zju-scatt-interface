"""Bulk inspection must follow named axes rather than average or flatten grids."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zju_scatt_interface.optics.models import BulkOptics
from zju_scatt_interface.plotting.bulk import plot_bulk_optics


def dataset(data, dimensions, units="1"):
    return {"data":np.asarray(data).tolist(),"dimensions":dimensions,"units":units}


def grid():
    # Unsorted coordinates and a non-last angle axis detect positional slicing.
    w=np.array([11.,10.,12.]);t=np.array([260.,220.,240.]);r=np.array([5.,1.,4.,2.,3.])
    angles=np.array([0.,45.,90.,135.,180.])
    ext=w[:,None,None]+t[None,:,None]/100+r[None,None,:]
    p=1+t[:,None,None,None]/1000+np.cos(np.deg2rad(angles))[None,:,None,None]**2+r[None,None,:,None]/10+w[None,None,None,:]/100
    dims=["wavelength","temperature","effective_radius"]
    pdims=["temperature","sca_angle","effective_radius","wavelength"]
    fields={"wavelength":dataset(w,["wavelength"],"um"),"temperature":dataset(t,["temperature"],"K"),
        "effective_radius":dataset(r,["effective_radius"],"um"),"sca_angle":dataset(angles,["sca_angle"],"degree"),
        "beta_ext":dataset(ext,dims,"m-1"),"beta_sca":dataset(.8*ext,dims,"m-1"),
        "beta_abs":dataset(.2*ext,dims,"m-1"),"ssa":dataset(np.full(ext.shape,.8),dims),
        "g":dataset(np.full(ext.shape,.6),dims),"number_concentration":dataset(np.ones(ext.shape),dims,"cm-3"),
        "psd_size":dataset(np.arange(1,101),["psd_size"],"um")}
    for name,factor in (("p11",1),("p12",-.1),("p22",.9),("p33",.8),("p44",.7),("p43",.05)):
        fields[name]=dataset(p*factor,pdims)
    return {"components":{"ice":{"datasets":fields}},"datasets":{}}


def fake_save(figure,path,**kwargs):
    Path(path).touch()


class BulkPlotTests(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_named_dimensions_three_phase_curves_and_middle_state(self):
        content=grid();before=copy.deepcopy(content)
        with tempfile.TemporaryDirectory() as directory, patch("matplotlib.figure.Figure.savefig",fake_save):
            result=plot_bulk_optics(content,output_dir=directory)
            detail=result["inspection"]["components"]["ice"]
            self.assertEqual(set(detail["dimensions"]),{"wavelength","temperature","effective_radius"})
            self.assertEqual(len(result["files"]),6)
            phase=result["figures"]["ice/phase_effective_radius"]
            self.assertEqual([len(axis.lines) for axis in phase.axes],[3]*6)
            selected=detail["phase_plots"]["phase_effective_radius"]
            self.assertEqual([item["index"] for item in selected["selected"]],[1,4,0])
            self.assertEqual(selected["fixed"]["temperature"]["index"],2)
            self.assertEqual(selected["fixed"]["wavelength"]["index"],0)
            angles=np.array([0.,45.,90.,135.,180.])
            np.testing.assert_allclose(phase.axes[0].lines[0].get_ydata(),
                1+.240+np.cos(np.deg2rad(angles))**2+.1+.11)
            np.testing.assert_allclose(phase.axes[1].lines[0].get_ydata(),.1)
            scalar=result["figures"]["ice/scalar_effective_radius"]
            np.testing.assert_allclose(scalar.axes[0].lines[0].get_xdata(),[1,2,3,4,5])
            np.testing.assert_allclose(scalar.axes[0].lines[0].get_ydata(),11+2.4+np.arange(1,6))
            self.assertEqual(scalar.axes[0].get_xscale(),"log")
            self.assertIn("temperature = 240 K",phase._suptitle.get_text())
            self.assertTrue(all(path.is_file() for files in result["files"].values() for path in files.values()))
            self.assertEqual(json.loads(result["report_file"].read_text()),result["inspection"])
        self.assertEqual(content,before)
        self.assertEqual(plt.get_fignums(),[])

    def test_single_state_actual_exports_and_bulk_object(self):
        angles=[0,90,180];p=np.zeros((3,4,4));p[:,0,0]=1
        bulk=BulkOptics(1.e-4,.8e-4,.2e-4,.8,.5,phase_matrix=p.tolist(),
            number_concentration=10,metadata={"scattering_angles_degrees":angles,
                "bulk_coefficient_unit":"m-1","number_concentration_output_unit":"cm-3"})
        with tempfile.TemporaryDirectory() as directory:
            result=plot_bulk_optics(bulk,output_dir=directory)
            self.assertEqual(set(result["files"]),{"bulk/scalar_state","bulk/phase_state"})
            self.assertTrue(result["files"]["bulk/phase_state"]["png"].read_bytes().startswith(b"\x89PNG"))
            self.assertEqual(len(result["figures"]["bulk/phase_state"].axes[0].lines),1)

    def test_missing_phase_scalar_only_and_style_isolation(self):
        content={"components":{"dust":{"datasets":{"wavelength":dataset([1,2],["wavelength"],"um"),
            "beta_ext":dataset([.1,.2],["wavelength"],"m-1")}}}}
        before=dict(matplotlib.rcParams)
        with tempfile.TemporaryDirectory() as directory, patch("matplotlib.figure.Figure.savefig",fake_save):
            result=plot_bulk_optics(content,output_dir=directory)
            self.assertEqual(set(result["files"]),{"dust/scalar_wavelength"})
            self.assertEqual([len(axis.lines) for axis in result["figures"]["dust/scalar_wavelength"].axes],[1,0,0,0])
        self.assertEqual(dict(matplotlib.rcParams),before)

    def test_partial_phase_missing_elements_not_invented(self):
        content={"components":{"dust":{"datasets":{"sca_angle":dataset([0,90,180],["sca_angle"],"degree"),
            "p11":dataset([1,1,1],["sca_angle"])}}}}
        with tempfile.TemporaryDirectory() as directory, patch("matplotlib.figure.Figure.savefig",fake_save):
            result=plot_bulk_optics(content,output_dir=directory)
            self.assertEqual([len(axis.lines) for axis in result["figures"]["dust/phase_state"].axes],[1,0,0,0,0,0])

    def test_bad_dimensions_fail_before_writing(self):
        content=grid()
        content["components"]["ice"]["datasets"]["beta_ext"]["dimensions"]=["wrong"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"dimension metadata"):
                plot_bulk_optics(content,output_dir=directory)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_netcdf_and_hdf5_command_read_dimension_metadata(self):
        import h5py
        from netCDF4 import Dataset

        from zju_scatt_interface.cli.plotting import run_bulk_optics_plot
        fields=grid()["components"]["ice"]["datasets"]
        with tempfile.TemporaryDirectory() as directory, patch("matplotlib.figure.Figure.savefig",fake_save):
            for extension in ("nc","h5"):
                path=Path(directory)/f"bulk.{extension}"
                if extension=="nc":
                    with Dataset(path,"w") as handle:
                        group=handle.createGroup("ice")
                        for name,entry in fields.items():
                            for dim,length in zip(entry["dimensions"],np.shape(entry["data"])):
                                if dim not in group.dimensions:
                                    group.createDimension(dim,length)
                        for name,entry in fields.items():
                            variable=group.createVariable(name,"f8",entry["dimensions"])
                            variable[:]=entry["data"];variable.units=entry["units"]
                else:
                    with h5py.File(path,"w") as handle:
                        group=handle.create_group("ice")
                        for name,entry in fields.items():
                            variable=group.create_dataset(name,data=entry["data"])
                            variable.attrs["dimensions"]=json.dumps(entry["dimensions"])
                            variable.attrs["units"]=entry["units"]
                result=run_bulk_optics_plot([str(path)])
                self.assertEqual(result["output_dir"],Path(directory)/"bulk_bulk_plots")
                self.assertEqual(len(result["figures"]),6)
                self.assertEqual(result["inspection"]["components"]["ice"]["scattering_angle"]["count"],5)

    def test_two_coordinate_points_do_not_duplicate_phase_lines(self):
        content={"components":{"dust":{"datasets":{"radius":dataset([1,2],["radius"],"um"),
            "sca_angle":dataset([0,90,180],["sca_angle"],"degree"),
            "p11":dataset([[1,1,1],[2,2,2]],["radius","sca_angle"])}}}}
        with tempfile.TemporaryDirectory() as directory, patch("matplotlib.figure.Figure.savefig",fake_save):
            result=plot_bulk_optics(content,output_dir=directory)
            self.assertEqual(len(result["figures"]["dust/phase_radius"].axes[0].lines),2)


if __name__=="__main__":
    unittest.main()
