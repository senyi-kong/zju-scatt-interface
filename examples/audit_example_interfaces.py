"""Audit each maintained example against the currently imported local interface.

No network or optical downloads. Optional --run executes only an explicit list
of synthetic examples; all other scripts receive safe --help checks where available.
Generated/source-snapshot files under downloads are not editable examples.
"""
import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import importlib
import inspect
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys


SYNTHETIC = {"example_03_bulk_scheme_validation.py", "example_04_observed_psd_csv.py",
    "example_05_interpolation_modes.py", "example_09_phase4_psd_validation.py",
    "example_10_phase5_interpolation_validation.py", "example_11_phase6_particle_adapter_validation.py",
    "example_12_phase7_bulk_pipeline_validation.py", "example_13_phase8_output_validation.py",
    "example_14_phase9_typed_and_cli_validation.py", "example_15_phase10_usability_validation.py",
    "example_17_native_model_formats.py"}


def audit_static(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    imported = {}; errors = []; checked = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("zju_scatt_interface"):
            try:
                module = importlib.import_module(node.module)
                for alias in node.names:
                    if alias.name != "*":
                        imported[alias.asname or alias.name] = getattr(module, alias.name)
            except (ImportError, AttributeError) as exc:
                errors.append(f"line {node.lineno}: {exc}")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        value = imported.get(node.func.id) if isinstance(node.func, ast.Name) else None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            parent = imported.get(node.func.value.id)
            if inspect.ismodule(parent):
                value = getattr(parent, node.func.attr, None)
        if value is None or not callable(value) or any(isinstance(a, ast.Starred) for a in node.args):
            continue
        keys = [k.arg for k in node.keywords if k.arg]
        if getattr(value,"__name__","") == 'retrieve_sources' and not node.args and "args" not in keys:
            from zju_scatt_interface.access.requests import make_retrieval_args
            value = make_retrieval_args
            keys = [key for key in keys if key != "client"]
        try:
            signature = inspect.signature(value)
        except (ValueError, TypeError):
            continue
        try:
            binder = signature.bind_partial if any(k.arg is None for k in node.keywords) else signature.bind
            binder(*[None]*len(node.args), **dict.fromkeys(keys))
            checked += 1
        except TypeError as exc:
            errors.append(f"line {node.lineno}: {getattr(value,'__name__',str(value))}: {exc}")
    return tree, {"syntax":"passed", "package_imports_and_signatures":"failed" if errors else "passed",
                  "calls_checked":checked, "errors":errors}


def audit_config(path):
    from zju_scatt_interface.bulk.tables import load_table_config
    from zju_scatt_interface.bulk.grid import load_grid_scheme
    from zju_scatt_interface.config.scheme import load_scheme
    values = runpy.run_path(str(path)) if path.suffix==".py" else json.loads(path.read_text())
    if path.suffix==".json" and "particle_types" in values:
        from zju_scatt_interface.cli.parser import build_parser
        from zju_scatt_interface.access.requests import build_retrieve_runtime_args
        args=build_parser().parse_args(["retrieve","--config",str(path),"--no-download"])
        build_retrieve_runtime_args(args)
        return "CLI JSON retrieval request validated without network access"
    if "EXAMPLES" in values and "PSD_SETTINGS" in values:
        from zju_scatt_interface.bulk.ensemble import WeightedShapeEnsemble
        from zju_scatt_interface.psd.analytical import lognormal_psd
        from zju_scatt_interface.bulk.workflow import compute_population
        lognormal_psd(**values["PSD_SETTINGS"])
        inspect.signature(compute_population).bind_partial(**values["CALCULATION_OPTIONS"])
        for settings in values["EXAMPLES"].values():
            WeightedShapeEnsemble.from_shapes(settings["shapes"],settings["weights"])
        return "shared ensemble inputs, PSD and calculation options validated"
    if "retrieval" in values:
        from zju_scatt_interface.access.workflow import load_retrieval_config
        from zju_scatt_interface.access.workflow import _requests
        from zju_scatt_interface.access.requests import make_retrieval_args
        jobs,_ = _requests(load_retrieval_config(path))
        for job in jobs.values():
            make_retrieval_args(**job)
        return "retrieval configuration and request options validated"
    if "bulk_table" in values:
        load_table_config(path); return "bulk_table configuration loaded"
    if "multi_bulk_scheme" in values:
        load_grid_scheme(path); return "multidimensional configuration loaded"
    if "bulk_scheme" in values or ("particles" in values and any(key in values for key in ("wavelengths","wavelengths_um"))):
        load_scheme(path).validate(); return "scheme configuration validated"
    return "input file executed/decoded; model-specific configuration checked by its example"


def audit_header(tree):
    header = ast.get_docstring(tree) or ""
    required = ("Role:", "Inputs:", "Outputs:", "Run:", "Notes:")
    missing = [name for name in required if name not in header]
    return {"status":"failed" if missing else "passed", "missing_sections":missing}


def check_script(path, tree, output, execute, cached_args=None):
    literals = {node.value for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str)}
    help_safe = any(token in path.read_text(encoding="utf-8-sig") for token in ("argparse","zju_scatt_interface.cli.retrieval import retrieve_from_config","zju_scatt_interface.cli.main import main as run_command")) or path.name in {
        "25_custom_shapes_rttov14.py","28_plot_single_scattering.py","29_plot_bulk_optics.py"}
    if not help_safe and cached_args is None:
        return {"execution":"not_run", "reason":"No help entry point; default workflow not executed"}
    commands = [("help",["--help"])] if help_safe else []
    if cached_args is not None:
        commands.append(("cached_run",cached_args))
    if execute and path.name in SYNTHETIC:
        target = output / "runs" / path.stem
        arguments = (["--output-dir",str(target)] if "--output-dir" in literals else
                     ["--output",str(target)] if "--output" in literals else [])
        commands.append(("synthetic_run",arguments))
    result = {}
    env = {**os.environ,"MPLBACKEND":"Agg","OPENBLAS_NUM_THREADS":"1"}
    for label,arguments in commands:
        logdir = output/"logs"/path.parent.name
        logdir.mkdir(parents=True,exist_ok=True)
        log = logdir/f"{path.stem}_{label}.txt"
        try:
            command=[sys.executable,str(path),*arguments]
            if label=="cached_run":
                guard=("import runpy,socket,sys\n"
                       "def deny(*args,**kwargs): raise RuntimeError('Audit forbids network access')\n"
                       "socket.socket.connect=deny\n"
                       "sys.argv=sys.argv[1:]\nrunpy.run_path(sys.argv[0],run_name='__main__')")
                # runpy does not add the script directory as Python normally does.
                env["PYTHONPATH"]=str(path.parent)+os.pathsep+env.get("PYTHONPATH","")
                command=[sys.executable,"-c",guard,str(path),*arguments]
            completed = subprocess.run(command,cwd=path.parent,
                env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
            log.write_text(completed.stdout,encoding="utf-8")
            result[label] = {"status":"passed" if completed.returncode==0 else "failed",
                             "exit_code":completed.returncode,"log":str(log)}
        except subprocess.TimeoutExpired as exc:
            result[label] = {"status":"timeout","error":str(exc)}
    if "synthetic_run" not in result and "cached_run" not in result:
        result["execution"] = "help_only; scientific workflow not executed"
    return result


def cached_cases(local, output):
    """Explicit cached-source plans/exports; never recalculate large lookup grids."""
    downloads=local/"downloads"
    runs=output/"runs";runs.mkdir(parents=True,exist_ok=True)
    cases={}
    cases["01_database_overview.py"]=["--offline"]
    cases["local_environment.py"]=[]
    reports=[downloads/folder/filename for folder,filename in (
        ("multispecies_1.5um","download_report.json"),("multispecies_1.5um_smoke","download_report.json"),
        ("bc_1.6um_v1.2.1_interpolation","interpolation_report.json"))]
    if all(path.is_file() for path in reports):
        cases["07_audit_native_outputs.py"]=["--reports",*[str(path) for path in reports],
            "--output-dir",str(runs/"native_schema_check")]
    for script,folder in {
        "03_download_seasalt_1p5um.py":"all_species_1.5um/coated_super_spheroid_seasalt",
        "10_download_ice_250k_1p6um.py":"ice_250K_1.6um",
        "11_download_ice_250k_1p6um_shape_interpolation.py":"ice_250K_1.6um_n2.1_asp1.7",
        "12_download_super_spheroid_explicit_index.py":"super_spheroid_n2.1_asp1.7_ref1.51_0.0023",
        "14_super_spheroid_lognormal_bulk_optics.py":"super_spheroid_lognormal_bulk",
        "15_super_spheroid_lognormal_shape_average.py":"super_spheroid_lognormal_shape_average",
        "16_super_spheroid_interpolated_shapes_bulk.py":"super_spheroid_interpolated_shapes_bulk",
    }.items():
        manifest=downloads/folder/"selection_manifest.jsonl"
        if manifest.is_file():
            cases[script]=["--manifest",str(manifest),"--list-only","--output-dir",str(runs/Path(script).stem)]
    dust=downloads/"dust_and_bc_explicit_indices/dust/selection_manifest.jsonl"
    bc=downloads/"dust_and_bc_explicit_indices/black_carbon/selection_manifest.jsonl"
    if dust.is_file() and bc.is_file():
        cases["13_download_dust_and_bc_explicit_indices.py"]=["--dust-manifest",str(dust),
            "--bc-manifest",str(bc),"--list-only","--output-dir",str(runs/"explicit_two_species")]
    bulk=downloads/"all_species_rttov13_wavelength_sequence/bulk_optics_all_species.nc"
    if bulk.is_file():
        for prefix,driver,key in (("21_rttov14","21_default_bulk_rttov14.py","rttov_output"),
                ("22_crtm_ir","22_default_bulk_crtm_ir.py","crtm_output"),
                ("23_arts","23_default_bulk_arts.py","arts_output")):
            loaded=runpy.run_path(str(local/f"{prefix}_config.py"))
            config=runs/f"{prefix}_config.py"
            settings={**loaded["bulk_table"],"output_dir":str(runs/prefix)}
            config.write_text(f"bulk_table = {settings!r}\n{key} = {loaded[key]!r}\n",encoding="utf-8")
            cases[driver]=["--config",str(config),"--reuse-bulk",str(bulk)]
        loaded=runpy.run_path(str(local/"27_custom_output_config.py"))
        specs=[]
        for entry in loaded["outputs"]:
            extension="h5" if entry["format"]=="hdf5" else "nc"
            specs.append({**entry,"filename":str(runs/"custom_output"/f"user_optics.{extension}")})
        config=runs/"custom_output_config.py"
        config.write_text(f"bulk_source = {str(bulk)!r}\noutputs = {specs!r}\n",encoding="utf-8")
        cases["27_export_custom_output.py"]=["--config",str(config),"--overwrite"]
    for script in ("28_plot_single_scattering.py","29_plot_bulk_optics.py"):
        cases[script]=["--output-dir",str(runs/Path(script).stem)]
    for config_name,script in (("24_rttov14_lookup_config.py","24_default_bulk_rttov14_lookup.py"),
                               ("25_custom_shapes_rttov14_config.py","25_custom_shapes_rttov14.py")):
        settings=runpy.run_path(str(local/config_name))
        masters=[Path(settings["output_dir"])/f"rttov_{root}_zju_lookup.nc" for root in ("aertable","hydrotable")]
        if all(path.is_file() for path in masters):
            directory=runs/Path(script).stem;directory.mkdir(parents=True,exist_ok=True)
            for path in masters:
                shutil.copy2(path,directory/path.name)
            config=runs/config_name
            config.write_text(f"output_dir = {str(directory)!r}\nnative_slice = {settings['native_slice']!r}\n",encoding="utf-8")
            cases[script]=["--config",str(config),"--slice-only"]
    loaded=runpy.run_path(str(local/"26_rttov14_two_letter_config.py"))
    if (Path(loaded["source_dir"])/"native_slice/selection.json").is_file():
        config=runs/"26_config.py"
        config.write_text(f"source_dir = {str(loaded['source_dir'])!r}\noutput_dir = {str(runs/'two_letter_names')!r}\n"
                          f"output_names = {loaded['output_names']!r}\n",encoding="utf-8")
        cases["26_default_scheme_rttov14_two_letter.py"]=["--config",str(config)]
    return cases


def run_audit(output, execute=False, cached=False):
    project = Path(__file__).resolve().parents[1]
    workspace = project.parent
    folders = [project/"examples",project/"configs",workspace/"test_zju_scatt/user_test_local",
               workspace/"test_zju_scatt/user_test"]
    paths = sorted({path for folder in folders for path in folder.glob("*.py")
                    if path.resolve() != Path(__file__).resolve()})
    paths += sorted((project/"configs").rglob("*.json"))
    paths += sorted((workspace/"test_zju_scatt/user_test_local").glob("*.json"))
    output = Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    cases=cached_cases(workspace/"test_zju_scatt/user_test_local",output) if cached else {}
    records = []
    pending = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for path in paths:
            record = {"path":str(path.relative_to(workspace))};records.append(record)
            try:
                tree, checks = audit_static(path) if path.suffix==".py" else (None,{"json":"passed"})
                record.update(checks)
                if tree is not None:
                    record["header"] = audit_header(tree)
                    if record["header"]["status"] == "failed":
                        record.setdefault("errors",[]).append("Missing descriptive header sections: " + ", ".join(record["header"]["missing_sections"]))
                is_config = path.parent.name=="configs" or "config" in path.stem or path.suffix==".json"
                if is_config:
                    record["configuration"] = audit_config(path)
                elif tree is not None:
                    pending.append((record,pool.submit(check_script,path,tree,output,execute,
                        cases.get(path.name) if path.parent.name=="user_test_local" else None)))
            except Exception as exc:
                record["audit_error"] = f"{type(exc).__name__}: {exc}"
        for record,future in pending:
            record.update(future.result())
    failed = [r for r in records if r.get("errors") or r.get("audit_error") or
              any(r.get(label,{}).get("status") in ("failed","timeout") for label in ("help","synthetic_run","cached_run"))]
    payload = {"python":sys.executable,"file_count":len(records),"failed_count":len(failed),"files":records}
    (output/"audit.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    lines = ["# Example interface audit", "", f"Files: {len(records)}. Failures: {len(failed)}.", "",
             "Signature checks are static; help checks do not run scientific calculations.",
             "Synthetic examples run end to end. Cached plans/exports run with network connections blocked.",
             "Live downloads, full bulk tables, full lookup grids and packaging builds are not executed.","",
             "| File | Header | Imports/signatures | Execution |", "|---|---|---|---|"]
    for record in records:
        execution = record.get("configuration") or "; ".join(f"{key}: {record[key]['status']}"
            for key in ("help","synthetic_run","cached_run") if key in record) or record.get("reason","")
        error = record.get("audit_error") or "; ".join(record.get("errors",[]))
        lines.append(f"| `{record['path']}` | {record.get('header',{}).get('status','JSON input')} | {error or record.get('package_imports_and_signatures','JSON decoded')} | {execution} |")
    (output/"AUDIT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"Audited {len(records)} files; {len(failed)} failed. Report: {output/'AUDIT.md'}",flush=True)
    for record in failed:
        print(json.dumps(record),flush=True)
    return int(bool(failed))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--cached",action="store_true",help="Also check explicit local cached-source selection/export cases")
    args=parser.parse_args()
    raise SystemExit(run_audit(args.output_dir,args.run,args.cached))
