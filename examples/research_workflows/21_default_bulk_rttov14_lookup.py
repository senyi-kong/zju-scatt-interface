"""Build RTTOV14 lookup cubes over PSD effective radius, RH and ice temperature, then select slices.

Role:
    Production example

Inputs:
    21_rttov14_lookup_config.py and native source report/catalog; --slice-only reuses masters.

Outputs:
    Master lookup cubes, selected runtime tables and metadata; BC vf fixed without RH.

Run:
    python 21_default_bulk_rttov14_lookup.py; append --help for options.

Notes:
    Compatible source coverage and selected optional dependencies are required. Inspect the
    input/output settings before running.
"""
import argparse
import json
from pathlib import Path
import runpy

from local_environment import verify_local_import
verify_local_import()
from zju_scatt_interface.io.applications.rttov.lookup import build_rttov14_lookup_tables
from zju_scatt_interface.io.applications.rttov.lookup import write_rttov14_lookup_slice


def _family_source_paths(sources,family):
    # Model names can share prefixes; match the complete cache-directory name.
    return [str(s.cache_path) for s in sources if family in Path(s.cache_path).parts]


def main(default_config=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=default_config or Path(__file__).with_name("21_rttov14_lookup_config.py"))
    parser.add_argument("--slice-only",action="store_true",help="Reselect existing master files without recalculating")
    parser.add_argument("--offline",action="store_true",help="Use only locally available native sources")
    args=parser.parse_args()
    settings=runpy.run_path(str(args.config))
    output=Path(settings["output_dir"])
    if not args.slice_only:
        report=json.loads(Path(settings["source_report"]).read_text(encoding="utf-8"))
        sources={family:[s["path"] for s in entry["sources"]] for family,entry in report["species"].items()}
        # Plan every ice temperature and all explicitly changed particle shapes.
        from zju_scatt_interface.config.scheme import Scheme
        from zju_scatt_interface.config.scheme import ParticleComponent
        from zju_scatt_interface.psd.models import SizeDistribution
        from zju_scatt_interface.bulk.tables import resolve_bulk_settings
        from zju_scatt_interface.sources.planning import prepare_scheme_dependencies
        from zju_scatt_interface.access.retrieval import retrieve_sources
        import contextlib
        import io
        from zju_scatt_interface.config.particles import get_particle_profile
        overrides={get_particle_profile(k).particle_type:v for k,v in settings.get("overrides",{}).items()}
        particles=[]
        for family in dict.fromkeys(["super_spheroid_ice",*overrides]):
            for state in ([{"temperature":t} for t in settings["ice_temperatures_k"]]
                          if family=="super_spheroid_ice" else [{}]):
                resolved=resolve_bulk_settings(family,{**overrides.get(family,{}),**state})
                particles.append(ParticleComponent(f"selected_{len(particles)}",family,
                    SizeDistribution([1.,2.],[.5,.5]),resolved["refractive_index"],
                    resolved["parameters"],tuple(resolved["shape_ensemble"])))
        plan_config=Scheme("lookup_sources",tuple(settings["wavelengths_um"]),tuple(particles),
                                    include_phase_matrix=True)
        def search(query):
            with contextlib.redirect_stdout(io.StringIO()):
                result=retrieve_sources(manifest=(settings.get("catalog") if settings.get("catalog") and Path(settings["catalog"]).is_file() else None),**query.retrieval_parameters)
            if result.status_code:
                raise RuntimeError(f"Lookup source selection failed: {result.status_code}")
            return result.objects
        print("Preparing sources for requested shapes and ice temperatures",flush=True)
        plan=prepare_scheme_dependencies(plan_config,workspace=settings["source_workspace"],
            offline=args.offline,searcher=search,reuse_dirs=[Path(settings["source_report"]).parent,
                                                         Path.home()/".cache/zju_scatt_interface"])
        if not plan.complete:
            raise ValueError("Incomplete lookup sources: "+"; ".join(issue.reason for issue in plan.issues))
        for family in dict.fromkeys(p.particle_type for p in particles):
            sources[family]=_family_source_paths(plan.sources,family)
        build_rttov14_lookup_tables(wavelengths=settings["wavelengths_um"],source_paths=sources,
            effective_radii_um=settings["effective_radii_um"],
            relative_humidity_percent=settings["relative_humidity_percent"],
            ice_temperatures_k=settings["ice_temperatures_k"],output_dir=output,
            sea_salt_branch=settings.get("sea_salt_branch","deliquescence"),
            bins=settings.get("bins",160),max_moments=settings.get("max_moments",32),
            overrides=settings.get("overrides"))
    selected=settings["native_slice"]
    validations={}
    for root in ("aertable","hydrotable"):
        target=output/"native_slice"/f"rttov_{root}_zju_selected.nc"
        validations[root]=write_rttov14_lookup_slice(output/f"rttov_{root}_zju_lookup.nc",target,**selected)
        print(f"Selected RTTOV14 table: {target}")
    (output/"native_slice"/"selection.json").write_text(json.dumps({
        "selection":selected,"validation":validations,
        "profiles":{"mmr_aer":False,"mmr_hydro":False,"nhydro":2},
        "note":"Aerosols: cm-3, RH-dependent at selected size. Clouds: g/m3, size-dependent at selected ice temperature."},indent=2),encoding="utf-8")
    print(f"Master lookup cubes: {output}")
    print("BC vf fixed, no BC RH axis. Master cubes require selection or a custom runtime adapter.")


if __name__=="__main__":
    main()
