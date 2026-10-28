"""Plot raw single-particle arrays without integrating or changing their phase."""
import copy
import tempfile
import unittest
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zju_scatt_interface.optics.models import SingleParticleOptics
from zju_scatt_interface.plotting.single import (
    OpticalPlotStyle,
    plot_single_particle_optics,
    plot_single_scattering,
)


def fixture():
    phase=np.zeros((3,3,4,4));phase[:,:,0,0]=2.;phase[:,:,0,1]=-.2;phase[:,:,3,2]=.4
    return SingleParticleOptics(sizes=[.1,1.,10.],extinction_cross_section=[1e-15,1e-13,1e-11],
        scattering_cross_section=[.8e-15,.8e-13,.8e-11],absorption_cross_section=[.2e-15,.2e-13,.2e-11],
        asymmetry_factor=[0.,.5,.9],phase_matrix=phase.tolist(),scattering_angles=[0,90,180],
        size_unit="um",cross_section_unit="m2")


class SingleParticlePlotTests(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_default_panels_leave_missing_data_empty(self):
        data=fixture();data.asymmetry_factor=None
        result=plot_single_particle_optics(data)
        axes=result["properties"].axes
        self.assertEqual(len(axes),4)
        self.assertEqual([len(axis.lines) for axis in axes],[3,0,0,0])
        self.assertEqual(axes[1].get_ylabel(),"Efficiency")
        self.assertEqual(axes[3].get_ylabel(),"Asymmetry factor")
        self.assertEqual(len(axes[1].get_yticks()),0)
        self.assertIn("single_scattering_albedo",result["inspection"]["missing_fields"])
        self.assertIsNone(result["inspection"]["ssa_source"])
        self.assertEqual(len(result["phase"].axes),6)
        self.assertTrue(all(axis.get_xscale()=="log" for axis in axes))

    def test_partial_fields_and_shared_style_do_not_change_global_settings(self):
        data=fixture();data.extinction_efficiency=[.1,1,2]
        data.single_scattering_albedo=[.8,.8,.8]
        data.metadata.update(wavelength_um=1.6,temperature_k=250,n=2.1,aspect_ratio=1.7)
        before=dict(matplotlib.rcParams)
        result=plot_single_particle_optics(data,style=OpticalPlotStyle(font_size=12,
            line_width=2.5,scalar_layout=(1,4),phase_layout=(3,2),scalar_figsize=(18,4)))
        self.assertEqual(dict(matplotlib.rcParams),before)
        axes=result["properties"].axes
        self.assertEqual([len(axis.lines) for axis in axes],[3,1,1,1])
        np.testing.assert_array_equal(axes[1].lines[0].get_ydata(),[.1,1,2])
        self.assertEqual(axes[0].lines[0].get_linewidth(),2.5)
        self.assertEqual(axes[0].xaxis.label.get_fontsize(),12)
        self.assertIn("T = 250 K",result["properties"]._suptitle.get_text())
        self.assertEqual(axes[0].get_subplotspec().get_gridspec().get_geometry(),(1,4))
        with self.assertRaisesRegex(ValueError,"exactly 4"):
            OpticalPlotStyle(scalar_layout=(2,3))

    def test_scalar_only_input_needs_no_phase_options(self):
        data=fixture();data.phase_matrix=None;data.scattering_angles=None
        result=plot_single_particle_optics(data)
        self.assertIsNone(result["phase"])

    def test_one_call_saves_all_figures_and_closes_them(self):
        data=fixture();before=plt.get_fignums()
        with tempfile.TemporaryDirectory() as directory:
            result=plot_single_scattering(data,output_dir=directory)
            self.assertEqual(len(result["files"]),8)
            self.assertTrue(all(path.is_file() for path in result["files"].values()))
            import csv
            import json
            with result["files"]["csv"].open() as stream:
                rows=list(csv.reader(stream))
            self.assertEqual(len(rows),4)
            self.assertEqual(rows[1][-3:],["","",""])
            self.assertEqual(json.loads(result["files"]["report"].read_text())["size_count"],3)
        self.assertEqual(plt.get_fignums(),before)

    def test_one_call_scalar_only_does_not_require_phase(self):
        data=fixture();data.phase_matrix=None;data.scattering_angles=None
        with tempfile.TemporaryDirectory() as directory:
            result=plot_single_scattering(data,output_dir=directory)
            self.assertNotIn("phase_png",result["files"])
            self.assertEqual(len(result["files"]),5)

    def test_efficiency_is_not_bounded_by_one_or_two(self):
        data=fixture();data.extinction_efficiency=[.1,3.5,2.1]
        data.scattering_efficiency=[.05,2.9,1.8]
        result=plot_single_particle_optics(data)
        axis=result["properties"].axes[1]
        np.testing.assert_array_equal(axis.lines[0].get_ydata(),[.1,3.5,2.1])
        self.assertGreater(axis.get_ylim()[1],3.5)
        self.assertGreater(len(axis.get_yticks()),0)

    def test_native_phase_and_actual_nearest_size_preserved(self):
        data=fixture(); before=copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as directory:
            result=plot_single_particle_optics(data,output=Path(directory)/"size.png",
                phase_output=Path(directory)/"phase.png",phase_radii_um=[.11,1.1])
            self.assertTrue((Path(directory)/"phase.png").is_file())
        self.assertEqual(data,before)
        np.testing.assert_array_equal(result["properties"].axes[0].lines[0].get_ydata(),data.extinction_cross_section)
        np.testing.assert_array_equal(result["phase"].axes[0].lines[0].get_ydata(),[2.,2.,2.])
        np.testing.assert_allclose(result["phase"].axes[1].lines[0].get_ydata(),.1)
        np.testing.assert_allclose(result["phase"].axes[5].lines[0].get_ydata(),.2)
        self.assertEqual([r["actual_radius"] for r in result["inspection"]["phase_selection"]],[.1,1.])
        self.assertAlmostEqual(result["inspection"]["phase_selection"][0]["P11_half_integral"],2.)

    def test_bad_values_are_reported_and_logarithmic_gaps_are_explicit(self):
        data=fixture();data.extinction_cross_section=[0.,-1.,float("nan")];data.asymmetry_factor=[0.,1.2,float("nan")]
        result=plot_single_particle_optics(data)
        report=result["inspection"]
        self.assertEqual(report["fields"]["extinction_cross_section"]["nonfinite"],1)
        self.assertEqual(report["fields"]["extinction_cross_section"]["negative"],1)
        self.assertEqual(report["asymmetry_factor_outside_physical_range"],1)
        self.assertTrue(np.isnan(result["properties"].axes[0].lines[0].get_ydata()).all())

    def test_invalid_phase_selection_and_dimensions_raise(self):
        data=fixture()
        with self.assertRaisesRegex(ValueError,"within"):
            plot_single_particle_optics(data,phase_radii_um=[100.])
        data.phase_matrix=None
        with self.assertRaisesRegex(ValueError,"include_phase_matrix"):
            plot_single_particle_optics(data,phase_output="unused.png")
        data.sizes=[1.,1.,2.]
        with self.assertRaisesRegex(ValueError,"strictly increasing"):
            plot_single_particle_optics(data)


if __name__=="__main__":
    unittest.main()
