"""Multidimensional optical-axis packing, slice selection and realized PSD size."""
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset

from zju_scatt_interface.io.applications.rttov.lookup import (
    _radius_psd,
    _write_grid,
    validate_rttov14_lookup_table,
    write_rttov14_lookup_slice,
)
from zju_scatt_interface.psd.analytical import radius_moments


def item(axes):
    shape=tuple(len(v) for _,v in axes)+(2,)
    values=np.arange(np.prod(shape),dtype=float).reshape(shape)+1
    return {"axes":axes,"is_frozen":False,"ext":values,"ssa":np.full(shape,.8),
            "asym":np.full(shape,.6),"bpr":np.full(shape,.2),
            "lcoef":np.broadcast_to(np.array([1.,.6,.2]),shape+(3,)).copy()}


class RTTOV14GridTests(unittest.TestCase):
    def test_single_wavelength_master_can_be_sliced(self):
        # netCDF4 returns a scalar for a one-element numeric attribute.
        # Keep the spectral axis when selecting native runtime tables.
        with tempfile.TemporaryDirectory() as directory:
            master = Path(directory) / "master.nc"
            target = Path(directory) / "selected.nc"
            entry = item([("deff", np.array([2.0, 4.0])), ("relhum", np.array([0.0, 50.0]))])
            for name in ("ext", "ssa", "asym", "bpr"):
                entry[name] = entry[name][..., :1]
            entry["lcoef"] = entry["lcoef"][..., :1, :]
            _write_grid(master, "aertable", [10.0], {"dust": entry}, 2, master=True)
            report = write_rttov14_lookup_slice(master, target,
                aerosol_effective_radii_um={"dust": 1.0})
            self.assertTrue(report["valid"])
            with Dataset(target) as dataset:
                self.assertEqual(dataset["aertable/dust/ext"].shape[-1], 1)

    def test_script_source_selection_does_not_mix_dust_with_ice(self):
        driver=Path(__file__).resolve().parents[2]/"test_zju_scatt/user_test_local/24_default_bulk_rttov14_lookup.py"
        if not driver.is_file():
            self.skipTest("Local user example is not present in this package checkout")
        with patch.dict(sys.modules,{"local_environment":SimpleNamespace(verify_local_import=lambda:None)}):
            functions=runpy.run_path(str(driver))
        dust=Path("cache/Single_opt/super_spheroid/data/dust.nc")
        ice=Path("cache/Single_opt/super_spheroid_ice/data/ice.nc")
        salt=Path("cache/Single_opt/coated_super_spheroid_seasalt/data/salt.nc")
        sources=[SimpleNamespace(cache_path=p) for p in (dust,ice,salt)]
        self.assertEqual(functions["_family_source_paths"](sources,"super_spheroid"),[str(dust)])
        self.assertEqual(functions["_family_source_paths"](sources,"super_spheroid_ice"),[str(ice)])

    def test_realized_radius_fit_retains_parent_shape_and_concentration(self):
        for reference in ({"type":"lognormal","sigma_g":1.8},{"type":"gamma","effective_variance":1/3}):
            psd=_radius_psd(reference,2.,[.1,8.],120)
            self.assertAlmostEqual(radius_moments(psd)["realized_effective_radius_um"],2.,places=7)
            self.assertAlmostEqual(psd.number_concentration_cm3,1.)
            key="sigma_g" if reference["type"]=="lognormal" else "effective_variance"
            self.assertEqual(psd.metadata[key],reference[key])

    def test_rh_size_axes_and_native_slice_preserve_nonconstant_values(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"master.nc"; target=Path(directory)/"selected.nc"
            original=item([("relhum",np.array([0.,50.,99.])),("deff",np.array([.2,.4]))])
            _write_grid(source,"aertable",[10.,11.],{"sulfate":original},2,master=True)
            with Dataset(source,"a") as nc:
                nc.wavelengths_um=[10.,11.]
            with Dataset(source) as nc:
                self.assertEqual(nc["aertable/sulfate/ext"].shape,(1,1,2,3,2))
                np.testing.assert_array_equal(nc["aertable/sulfate/ext"][0,0,1],original["ext"][:,1])
            result=write_rttov14_lookup_slice(source,target,aerosol_effective_radii_um={"sulfate":.2})
            self.assertTrue(result["native_runtime_compatible"])
            with Dataset(target) as nc:
                np.testing.assert_array_equal(nc["aertable/sulfate/ext"][0,0,0],original["ext"][:,1])
                np.testing.assert_array_equal(nc["aertable/sulfate/dim_type"][:],[3,0,0,0])
            with self.assertRaisesRegex(ValueError,"exact lookup"):
                write_rttov14_lookup_slice(source,target,aerosol_effective_radii_um={"sulfate":.15})

    def test_size_temperature_slice_keeps_size_variation(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"ice.nc"; target=Path(directory)/"selected.nc"
            original=item([("deff",np.array([40.,60.])),("temperature",np.array([160.,220.,270.]))])
            _write_grid(source,"hydrotable",[10.,11.],{"ice":original},2,master=True)
            with Dataset(source,"a") as nc:
                nc.wavelengths_um=[10.,11.]
            write_rttov14_lookup_slice(source,target,ice_temperature_k=220.)
            with Dataset(target) as nc:
                np.testing.assert_array_equal(nc["hydrotable/ice/ext"][0,0,0],original["ext"][:,1])
                np.testing.assert_array_equal(nc["hydrotable/ice/deff"][:],[40,60])

    def test_unsupported_joint_axes_are_not_claimed_native(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"bad.nc"
            with self.assertRaisesRegex(ValueError,"Unsupported stock"):
                _write_grid(source,"aertable",[10.,11.],{"sulfate":item([
                    ("relhum",np.array([0.,99.])),("deff",np.array([.2,.4]))])},2,master=False)

    def test_all_species_build_computes_each_environment_and_size(self):
        from zju_scatt_interface.bulk.defaults import default_bulk_assumptions
        from zju_scatt_interface.io.applications.rttov.lookup import build_rttov14_lookup_tables
        from zju_scatt_interface.io.applications.rttov.v13 import AEROSOL_NAMES
        from zju_scatt_interface.io.applications.rttov.v14 import HYDROMETEOR_NAMES
        from zju_scatt_interface.optics.models import SingleParticleOptics
        names={**AEROSOL_NAMES,**HYDROMETEOR_NAMES}
        class Adapter:
            def resolve(self,paths,*,wavelength,parameters,**kwargs):
                factor=(1+parameters.get("relative_humidity",0))*parameters.get("temperature",220)/220
                def interpolate(*,target_size_um,**kw):
                    radii=np.asarray(target_size_um)
                    ext=1e-12*radii**2*factor
                    matrix=np.zeros((len(radii),181,4,4)); matrix[:,:,0,0]=1.
                    return SimpleNamespace(optics=SingleParticleOptics(
                        sizes=radii.tolist(),extinction_cross_section=ext.tolist(),
                        scattering_cross_section=(ext/2).tolist(),absorption_cross_section=(ext/2).tolist(),
                        asymmetry_factor=[0.]*len(radii),phase_matrix=matrix.tolist(),
                        scattering_angles=list(range(181)),size_unit="um",cross_section_unit="m2"))
                return SimpleNamespace(interpolate=interpolate,
                                       provenance=SimpleNamespace(to_dict=lambda:{}))
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.nc"; source.touch()
            with patch('zju_scatt_interface.sources.adapters.registry.get_particle_adapter',return_value=Adapter()),\
                 patch('zju_scatt_interface.bulk.tables.check_spectral_size_coverage',return_value={"common_source_radius_um":[.01,100.]}),\
                 patch('zju_scatt_interface.bulk.defaults.default_bulk_assumptions',side_effect=lambda family,**kw:{
                     **default_bulk_assumptions(family),"used_native_vf":.3}):
                result=build_rttov14_lookup_tables(wavelengths=[10.,11.],
                    source_paths={family:[source] for family in names},
                    effective_radii_um={name:[1.,2.] for name in names.values()},
                    relative_humidity_percent=[0.,99.],ice_temperatures_k=[160.,220.],
                    output_dir=directory,bins=30,max_moments=2,progress=None)
                custom=build_rttov14_lookup_tables(wavelengths=[10.,11.],
                    source_paths={family:[source] for family in names},
                    effective_radii_um={name:[1.,2.] for name in names.values()},
                    relative_humidity_percent=[0.,99.],ice_temperatures_k=[160.,220.],
                    output_dir=Path(directory)/"custom",bins=30,max_moments=2,progress=None,
                    overrides={"black_carbon":{"df":2.1,"vf":.4},
                        "dust":{"shapes":[{"ssph_n":2.8,"ssph_asp":.5},{"ssph_n":2.8,"ssph_asp":2.}]},
                        "ice":{"shapes":{"ssph_n":2.5,"ssph_asp":2.}}})
                self.assertEqual(custom["populations"]["black_carbon"]["fixed_parameters"]["vf"],.4)
                dust=custom["populations"]["dust"]["shape_ensemble"]
                self.assertEqual([m["weight"] for m in dust],[.5,.5])
                self.assertEqual([m["parameters"]["roundness"] for m in dust],[2.8,2.8])
                self.assertEqual([m["parameters"]["aspect_ratio"] for m in dust],[.5,2.])
                self.assertEqual(len(custom["populations"]["ice_cloud_zju_super_spheroid"]["shape_ensemble"]),1)
            with Dataset(result["outputs"]["aertable"]) as nc:
                self.assertEqual(nc["aertable/black_carbon/ext"].shape,(1,1,1,2,2))
                self.assertNotIn("relhum",nc["aertable/black_carbon"].variables)
                e=nc["aertable/sulfate/ext"][:]
                np.testing.assert_allclose(e[0,0,:,1]/e[0,0,:,0],1.99,rtol=1e-6)
                self.assertTrue(np.all(e[0,0,1]>e[0,0,0]))
            with Dataset(result["outputs"]["hydrotable"]) as nc:
                e=nc["hydrotable/ice_cloud_zju_super_spheroid/ext"][:]
                np.testing.assert_allclose(e[0,0,1]/e[0,0,0],220/160,rtol=1e-6)

    def test_native_seasalt_placeholder_size_reconstruction(self):
        from zju_scatt_interface.optics.loading import load_single
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"L1_coated_super_spheroid_seasalt_wl_10.000_um_ref_1.5_0.01.nc"
            with Dataset(path,"w") as nc:
                nc.createDimension("rh",2); nc.createDimension("xsize_maxd",3)
                nc.createVariable("rh","f8",("rh",))[:]=[90,99]
                nc.createVariable("xsize_maxd","f8",("xsize_maxd",))[:]=[1,2,3]
                nc.createVariable("ve","f8",("rh",))[:]=[1.1,1.2]
                nc.createVariable("xsize_veq","f8",("rh","xsize_maxd"))[:]=[[1.1,2.2,3.3],[1,1,1]]
                for name,value in (("cext",1.),("ssa",.8),("g",.4)):
                    nc.createVariable(name,"f8",("rh","xsize_maxd"))[:]=value
            a=load_single(path,size_dataset="xsize_veq",coordinate_indices={"rh":1})
            np.testing.assert_allclose(a.sizes,np.array([1.2,2.4,3.6])*10/(2*np.pi))
            self.assertIn("size_coordinate_reconstruction",a.metadata)
            with Dataset(path) as nc:
                np.testing.assert_array_equal(nc["xsize_veq"][1],[1,1,1])


if __name__=="__main__":
    unittest.main()
