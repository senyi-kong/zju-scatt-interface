"""Execute the local research examples against the active editable interface.

Run with the research environment's Python. Scientific settings are preserved;
only catalogs, source reuse, tracking and destinations are adapted for an isolated
run. No session is fabricated and no input/result directory is deleted.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
LOCAL = PROJECT.parent / "test_zju_scatt/user_test_local"
sys.path.insert(0, str(PROJECT / "examples"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", nargs="*", help="Repeat selected case identifiers")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    configs = output / "configs"; configs.mkdir(exist_ok=True)
    logs = output / "logs"; logs.mkdir(exist_ok=True)
    results = json.loads((output / "results.json").read_text()) if (output / "results.json").is_file() else {}
    from audit_example_interfaces import audit_static, audit_config
    from zju_scatt_interface.access.manifests import load_manifest, write_manifest
    from zju_scatt_interface.access.download import destination_for
    from zju_scatt_interface.access.workflow import load_retrieval_config, _requests
    from zju_scatt_interface.bulk.tables import load_table_config
    from zju_scatt_interface.access.models import RemoteObject
    from zju_scatt_interface.access.retrieval import retrieve_sources
    import zju_scatt_interface

    expected = (PROJECT / "src/__init__.py").resolve()
    if Path(zju_scatt_interface.__file__).resolve() != expected:
        raise RuntimeError("Wrong interface imported")
    index = {}
    for base in (Path.home() / ".cache/zju_scatt_interface", LOCAL / "downloads"):
        for path in base.rglob("*.nc"):
            if path.name.startswith(("L1_", "L1.5_")) and "interpolated" not in path.parts:
                index.setdefault(path.name, []).append(path)

    def persist():
        (output / "results.json").write_text(json.dumps(results, indent=2, default=str) + "\n")

    def execute(case, script, arguments, scope, network=False, cwd=None):
        if args.only and case not in args.only:
            return results.get(case, {}).get("status") == "passed"
        log = logs / f"{case}.log"
        print(f"START {case}: {scope}", flush=True)
        env = {**os.environ, "MPLBACKEND": "Agg", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        guard = "import sys,runpy\n"
        if not network:
            guard += "def deny(event,args):\n if event in {'socket.connect','socket.getaddrinfo'}: raise RuntimeError('Verification case forbids network access')\nsys.addaudithook(deny)\n"
        guard += "sys.argv=sys.argv[1:]\nsys.path.insert(0,str(__import__('pathlib').Path(sys.argv[0]).parent))\nrunpy.run_path(sys.argv[0],run_name='__main__')\n"
        command = [sys.executable, "-c", guard, str(script), *map(str, arguments)]
        started = time.monotonic()
        with log.open("w") as stream:
            completed = subprocess.run(command, cwd=cwd or LOCAL, env=env, stdout=stream, stderr=subprocess.STDOUT)
        results[case] = {"script": str(script), "arguments": list(map(str, arguments)), "scope": scope, "network_allowed": network,
            "status": "passed" if completed.returncode == 0 else "failed", "exit_code": completed.returncode,
            "seconds": round(time.monotonic()-started, 2), "log": str(log)}
        persist()
        print(f"END {case}: {results[case]['status']} ({results[case]['seconds']} s)", flush=True)
        if completed.returncode:
            print("\n".join(log.read_text(errors="replace").splitlines()[-12:]), flush=True)
        return completed.returncode == 0

    def write_config(name, content):
        path = configs / name
        path.write_text("from pathlib import Path, PosixPath\n" + content, encoding="utf-8")
        return path

    def cached_file(obj):
        candidates = [path for path in index.get(Path(obj.key).name, ()) if not obj.size or path.stat().st_size == obj.size]
        suffix = "Single_opt/" + obj.key.split("Single_opt/", 1)[-1]
        exact = [path for path in candidates if path.as_posix().endswith(suffix)]
        if not candidates: raise FileNotFoundError(f"No cached source: {obj.key}")
        return (exact or candidates)[0]

    def stage(objects, destination):
        missing = 0
        for obj in objects:
            target = destination_for(obj, destination, False)
            if target.is_file(): continue
            try:
                source = cached_file(obj)
            except FileNotFoundError:
                missing += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try: os.link(source, target)
            except OSError: shutil.copy2(source, target)
        return missing

    def catalog(directory, family, identifier):
        # Historical manifests use both JSONL and tab-separated text named .json.
        manifests = sorted(directory.glob("selection_manifest.*"))
        manifests += sorted(directory.glob("*/selection_manifest.*"))
        objects = {}
        for manifest in manifests:
            text = manifest.read_text(encoding="utf-8-sig")
            if text.lstrip().startswith("{"):
                loaded = load_manifest(manifest)
            else:
                loaded = []
                for line in text.splitlines():
                    if not line.strip(): continue
                    parts = line.split("\t")
                    loaded.append(RemoteObject(parts[0],int(parts[1]) if len(parts)>1 else 0,
                        parts[2] if len(parts)>2 else "",parts[3] if len(parts)>3 else ""))
            for obj in loaded:
                if f"Single_opt/{family}/" in obj.key:
                    objects[obj.key] = obj
        if not objects:
            # Some older interpolation reports retain source paths but no catalog.
            for report_path in directory.glob("*report.json"):
                report=json.loads(report_path.read_text())
                for product in report.get("interpolated_products", []):
                    if product.get("particle_type") != family: continue
                    for raw in product.get("source_paths", []):
                        path=Path(raw)
                        if path.is_file():
                            obj=RemoteObject(f"Single_opt/{family}/data/{path.name}",path.stat().st_size)
                            objects[obj.key]=obj
        if any(not index.get(Path(obj.key).name) for obj in objects.values()):
            # A broad historical catalog can reference uncached old BC grid data.
            # Prefer the complete current catalog, then reselect the unchanged request.
            master=LOCAL/"downloads/all_species_bulk_0p3_1p0um/catalog.jsonl"
            objects={obj.key:obj for obj in load_manifest(master) if f"Single_opt/{family}/" in obj.key}
        if not objects:
            raise FileNotFoundError(f"No saved selected-source catalog for {directory}, {family}")
        path = configs / f"{identifier}.jsonl"
        write_manifest(list(objects.values()), path, "jsonl")
        return path, list(objects.values())

    def retrieval_case(number, script):
        source = LOCAL / f"{number}_retrieval_config.py"
        config = load_retrieval_config(source)
        original_output = Path(config["output_dir"])
        jobs, _ = _requests(config)
        batch = "requests" in config or len(jobs) > 1
        target = output / "runs" / script.stem
        config["output_dir"] = str(target)
        config["no_track"] = True
        missing_sources = 0
        def prepare(saved,job,destination):
            nonlocal missing_sources
            selection=retrieve_sources(**{**job,"manifest":saved,"download":False,"quiet":True,
                "output_dir":destination,"manifest_output":None,"operation_log":None,"no_track":True})
            selection.raise_for_status(require_matches=True)
            missing_sources += stage(selection.objects,destination)
        if config.get("requests") == "all":
            for name, job in jobs.items():
                saved, objects = catalog(original_output, job["particle_types"], f"{number}_{name}")
                config.setdefault("overrides", {}).setdefault(name, {})["manifest"] = str(saved)
                prepare(saved,job,target/name)
        elif batch:
            for name, job in jobs.items():
                saved, objects = catalog(original_output/name, job["particle_types"], f"{number}_{name}")
                config["requests"][name]["manifest"] = str(saved)
                prepare(saved,job,target/name)
        else:
            saved, objects = catalog(original_output, next(iter(jobs.values()))["particle_types"], number)
            config["manifest"] = str(saved)
            prepare(saved,next(iter(jobs.values())),target)
        path = write_config(f"{number}_retrieval.py", f"retrieval = {config!r}\n")
        return execute(number, script, ["--config", path],
            f"full original retrieval coordinates; fresh products; {missing_sources} uncached sources may download",
            network=bool(missing_sources))

    # Every original top-level Python file is audited; configs are loaded using the API.
    if not args.only:
        for path in sorted(LOCAL.glob("*.py")):
            name = "static_" + path.stem
            try:
                tree, record = audit_static(path)
                if "config" in path.stem:
                    record["configuration"] = audit_config(path)
                record["status"] = "failed" if record["errors"] else "passed"
                results[name] = record
            except Exception:
                results[name] = {"status": "failed", "error": traceback.format_exc()}
        persist()

    scripts = {p.name[:2]: p for p in LOCAL.glob("[0-9][0-9]_*.py") if "config" not in p.stem}
    execute("environment", LOCAL/"local_environment.py", [], "actual editable import verification")
    execute("01", scripts["01"], [], "live catalog listing and all registered profile contracts", network=True)
    for number in ("02", "03", "04", "05", "08", "09", "10", "11", "12", "13"):
        if args.only and number not in args.only: continue
        try: retrieval_case(number, scripts[number])
        except Exception:
            results[number] = {"status": "failed", "error": traceback.format_exc()}; persist(); print(results[number]["error"], flush=True)

    # Native regeneration is intentionally confined to a copied report/output tree.
    if not args.only or "06" in args.only or "07" in args.only:
        original = LOCAL/"downloads/multispecies_1.5um_smoke/download_report.json"
        report = json.loads(original.read_text())
        root = output/"runs/native_regeneration"; root.mkdir(parents=True, exist_ok=True)
        for name, entry in report["species"].items():
            entry.setdefault("request", {})["output_dir"] = str(root/name)
            entry["request"]["interpolation_output_dir"] = str(root/name/"interpolated")
            for product in entry.get("interpolated_products", []):
                source=Path(product["path"]); target=root/name/source.name
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists(): shutil.copy2(source,target)
                product["path"] = str(target)
        copied=root/"download_report.json"; copied.write_text(json.dumps(report,indent=2))
        execute("06", scripts["06"], [copied], "native regeneration with original cached sources and isolated legacy copies")
        execute("07", scripts["07"], ["--reports",copied,"--output-dir",root], "audit newly regenerated native schemas and optical identities")

    for number, folder in (("14","super_spheroid_lognormal_bulk"),("15","super_spheroid_lognormal_shape_average"),("16","super_spheroid_interpolated_shapes_bulk")):
        if args.only and number not in args.only: continue
        try:
            saved, objects = catalog(LOCAL/"downloads"/folder, "super_spheroid", number)
            destination=output/"runs"/scripts[number].stem
            stage(objects,destination/"sources")
            execute(number,scripts[number],["--manifest",saved,"--no-track","--output-dir",destination],"original PSD, shapes, phases, QA/convergence and diagnostic/L2 exports")
        except Exception:
            results[number]={"status":"failed","error":traceback.format_exc()};persist();print(results[number]["error"],flush=True)

    table_reports = {"17":"all_species_bulk_0p3_1p0um_literature","18":"all_species_bulk_10p0_12p0um","19":"all_species_bulk_10p0_12p0um","20":"all_species_rttov13_wavelength_sequence"}
    config_names={"17":"17_bulk_table_config.py","18":"18_bulk_table_10p0_12p0um_config.py","19":"19_measured_psd_config.py","20":"20_rttov13_config.py","21":"21_rttov14_config.py","22":"22_crtm_ir_config.py","23":"23_arts_config.py"}
    for number in ("17","18","19","20","21","22","23"):
        if args.only and number not in args.only: continue
        original=LOCAL/config_names[number]
        settings=runpy.run_path(str(original)); config=load_table_config(original)
        base=vars(config).copy(); destination=output/"runs"/scripts[number].stem
        source_report=LOCAL/"downloads"/table_reports.get(number,"all_species_rttov13_wavelength_sequence")/"report.json"
        report=json.loads(source_report.read_text())
        base.update(output_dir=str(destination),workspace=str(output/"workspaces"/number),source_paths={k:[s["path"] for s in v["sources"]] for k,v in report["species"].items()},offline=True)
        extra="\n".join(f"{key} = {settings[key]!r}" for key in ("rttov_output","crtm_output","arts_output") if key in settings)
        conf=write_config(f"{number}_table.py",f"bulk_table = {base!r}\n{extra}\n")
        execute(number,scripts[number],["--config",conf,"--offline"],"full original species/spectrum/PSD and actual bulk calculation/export using local native inputs")

    # Full original lookup grids; no reduction of wavelengths, sizes, RH or temperature.
    for number, conf_name in (("24","24_rttov14_lookup_config.py"),("25","25_custom_shapes_rttov14_config.py")):
        if args.only and number not in args.only: continue
        original=LOCAL/conf_name
        target=output/"runs"/scripts[number].stem
        content=f"import runpy\nfrom pathlib import Path\nglobals().update({{k:v for k,v in runpy.run_path({str(original)!r}).items() if not k.startswith('__')}})\noutput_dir=Path({str(target)!r})\nsource_workspace=Path({str(output/'workspaces'/number)!r})\n"
        conf=write_config(f"{number}_lookup.py",content)
        execute(number,scripts[number],["--config",conf],"complete original lookup grids, all 8 species, followed by runtime slicing",network=True)

    if not args.only or "26" in args.only:
        settings=runpy.run_path(str(LOCAL/"26_rttov14_two_letter_config.py"))
        source=output/"runs"/scripts["24"].stem
        conf=write_config("26_naming.py",f"from pathlib import Path\nsource_dir=Path({str(source)!r})\noutput_dir=Path({str(output/'runs'/scripts['26'].stem)!r})\noutput_names={settings['output_names']!r}\n")
        execute("26",scripts["26"],["--config",conf],"rename newly calculated full default lookup grids without changing optics")
    if not args.only or "27" in args.only:
        settings=runpy.run_path(str(LOCAL/"27_custom_output_config.py"))
        specs=[{**spec,"filename":str(output/"runs"/scripts["27"].stem/Path(spec["filename"]).name)} for spec in settings["outputs"]]
        bulk=output/"runs"/scripts["20"].stem/"bulk_optics_all_species.nc"
        conf=write_config("27_output.py",f"bulk_source={str(bulk)!r}\noutputs={specs!r}\n")
        execute("27",scripts["27"],["--config",conf,"--overwrite"],"NetCDF/HDF5 custom layouts with read-back validation")
    for number, source in (("28",next(iter(sorted((output/"runs"/scripts["11"].stem/"interpolated").rglob("*.nc"))),None)),("29",output/"runs"/scripts["15"].stem/"application_outputs/bulk_optics_10_cm3.nc")):
        if args.only and number not in args.only: continue
        execute(number,scripts[number],([source] if source else [])+["--output-dir",output/"runs"/scripts[number].stem],"actual plots and dimension/selection reports")
    if not args.only or "30" in args.only:
        config=json.loads((LOCAL/"request.json").read_text()); old=LOCAL/"downloads/seasalt_1.5um"
        saved,objects=catalog(old,"coated_super_spheroid_seasalt","30")
        target=output/"runs"/scripts["30"].stem;stage(objects,target)
        config.update(manifest=str(saved),no_track=True,output_dir=str(target),manifest_output=str(target/"selection_manifest.jsonl"),operation_log=str(target/"operation.log"))
        conf=configs/"30_request.json";conf.write_text(json.dumps(config,indent=2))
        execute("30",scripts["30"],["--config",conf,"--output-dir",target],"JSON CLI retrieval with fresh native products")
    failures=[key for key,value in results.items() if value.get("status")!="passed"]
    print(json.dumps({"results":str(output/"results.json"),"checks":len(results),"failures":failures},indent=2),flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
