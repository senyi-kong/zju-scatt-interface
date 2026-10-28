"""Audit release example numbering, configurations and offline CLI entry points.

Run using the installed research environment. Optional --scientific exercises the
renumbered shared-config and delegated-driver paths against existing local data.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'examples'))
from audit_example_interfaces import audit_config, audit_static


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scientific', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = ROOT/'examples/research_workflows'
    files = sorted(base.glob('*.py'))
    drivers = [p for p in files if p.name[:2].isdigit() and 'config' not in p.stem]
    assert [p.name[:2] for p in drivers] == [f'{i:02}' for i in range(1,28)]
    results = {}
    for path in files:
        tree, record = audit_static(path)
        if 'config' in path.stem and path.name[:2].isdigit():
            record['configuration'] = audit_config(path)
        for ref in set(re.findall(r'\b[0-9]{2}_[A-Za-z0-9_]+\.py\b',path.read_text(encoding='utf-8'))):
            assert (base/ref).is_file(), (path.name,ref)
        record['status'] = 'failed' if record['errors'] else 'passed'
        results['static_'+path.stem] = record
    namespace = __import__('runpy').run_path(str(base/'ensemble_bulk_config.py'))
    assert set(namespace['EXAMPLES']) == {'12','13'}
    guard = "import sys,runpy\ndef deny(event,args):\n if event in {'socket.connect','socket.getaddrinfo'}: raise RuntimeError('Network forbidden in verification')\nsys.addaudithook(deny)\nsys.argv=sys.argv[1:]\nsys.path.insert(0,str(__import__('pathlib').Path(sys.argv[0]).parent))\nrunpy.run_path(sys.argv[0],run_name='__main__')\n"
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1', 'MPLBACKEND':'Agg', 'OPENBLAS_NUM_THREADS':'1'}

    def execute(name, path, arguments):
        log = args.output/(name+'.log')
        with log.open('w') as stream:
            result = subprocess.run([sys.executable,'-c',guard,str(path),*map(str,arguments)],
                cwd='/tmp' if os.name=='posix' else args.output,env=env,stdout=stream,stderr=subprocess.STDOUT)
        results[name] = {'status':'passed' if result.returncode==0 else 'failed',
            'script':path.name,'arguments':list(map(str,arguments)), 'exit_code':result.returncode,'log':str(log)}
        print(name,results[name]['status'],flush=True)

    for path in drivers:
        execute('help_'+path.stem,path,['--help'])
    execute('overview',drivers[0],['--offline'])
    if args.scientific:
        old = Path.home()/'.cache/zju_scatt_interface/release_examples_verification_20261027'
        for new, original in ((12,15),(13,16)):
            path = next(p for p in drivers if p.name.startswith(f'{new:02}_'))
            prior = next((old/'runs').glob(f'{original:02}_*'))
            target = args.output/'runs'/path.stem
            # Share immutable cached native inputs; produce fresh numerical outputs.
            for source in (prior/'sources').rglob('*'):
                if not source.is_file():
                    continue
                dest = target/'sources'/source.relative_to(prior/'sources')
                dest.parent.mkdir(parents=True,exist_ok=True)
                if not dest.exists():
                    os.link(source,dest)
            execute('population_'+str(new),path,['--manifest',old/'configs'/f'{original:02}.jsonl',
                '--no-track','--output-dir',target])
        for new, original in ((21,24),(22,25)):
            path = next(p for p in drivers if p.name.startswith(f'{new:02}_'))
            # Exercise the renamed shared-driver delegation against verified full cubes.
            execute('lookup_slice_'+str(new),path,['--config',old/'configs'/f'{original:02}_lookup.py','--slice-only'])
        path = next(p for p in drivers if p.name.startswith('27_'))
        execute('json_paths',path,['--config',old/'copied_json_path_check/request.json','--no-download'])
    failures = [key for key,value in results.items() if value['status']!='passed']
    summary = {'status':'failed' if failures else 'passed','python_files':len(files),
        'drivers':len(drivers),'network':'blocked','checks':results,'failures':failures}
    (args.output/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({'status':summary['status'],'failures':failures,'checks':len(results)}))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
