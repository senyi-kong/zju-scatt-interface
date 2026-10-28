# Workflow reference

<img src="../../../assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

Commands below run from a source project root with the package installed and
registration configured. All are single-line commands. Use installed `--help`
and `bulk-opt schema --json` to check options before adapting them.

## Route the request

| Request | Entry point | Matching source guide |
|---|---|---|
| Retrieve single-particle data | `zsi.retrieve(config)` | `docs/USER_MANUAL.md, section 5` |
| One population and wavelength, local sources | `zsi.compute_population(particle_type, source_paths, psd, wavelength=...)` | `docs/USER_MANUAL.md, section 7` |
| Several wavelengths/populations | `zsi.load_scheme`, `zsi.validate`, `zsi.plan`, `zsi.build` | `docs/USER_MANUAL.md, sections 4 and 8` |
| Analytical PSD | `zju_scatt_interface.psd.lognormal_psd` or `gamma_psd` | `docs/SCIENTIFIC_REFERENCE.md, section 2` |
| Reference spectral tables | `zju_scatt_interface.bulk.tables.build_table` | `docs/USER_MANUAL.md, section 8` |
| Inspect canonical bulk output | `zsi.validate(path)`, `zsi.read(path)`, `zsi.plot(path, kind="bulk")` | `docs/SCIENTIFIC_REFERENCE.md, section 6` |
| Model-specific export | `zju_scatt_interface.io.applications` specialist modules | `docs/SCIENTIFIC_REFERENCE.md, section 7` |

`zsi` means `import zju_scatt_interface as zsi`. Recipe arrays are demonstrations.
Read only the task-relevant guides; do not load the entire documentation tree.

## CLI scheme workflow

```console
python -m zju_scatt_interface bulk-opt schema --particle-type super_spheroid_ice --json
python -m zju_scatt_interface bulk-opt validate scheme.json --json --report validation.json
python -m zju_scatt_interface bulk-opt plan scheme.json --dry-run --json --report query_preview.json
python -m zju_scatt_interface bulk-opt plan scheme.json --workspace research_data --json --report dependency_plan.json
python -m zju_scatt_interface bulk-opt build scheme.json --workspace research_data --report build_report.json
```

Validation and dry-run on JSON are local. An explicit report writes a file even in
a dry-run. Ordinary plan may scan the catalog and create workspace/manifests, but
does not download optical files. An incomplete plan can exit `2` because files are
not cached; inspect each issue before deciding whether to build. A plan with local
`--source` overrides records paths but does not establish validity/coverage.

For offline use add `--offline` to plan/build and use a matching saved manifest and
verified cache. Explicit local `--source COMPONENT=PATH` overrides must cover all
components. A dry-run does not prove an offline build will work. Do not start an
online download merely because an offline cache check fails.

`build` performs calculation and file writing. In Python, these are separate:

```python
import zju_scatt_interface as zsi

scheme = zsi.load_scheme("scheme.json")
queries = zsi.validate(scheme)
plan = zsi.plan(scheme, workspace="research_data")
dataset = zsi.build(scheme, plan=plan)
zsi.write(dataset, "product.nc")
zsi.validate("product.nc").require_valid()
```

`build` refreshes incomplete plans and inherits their offline policy. Use `plan=`,
not `dependency_plan=`, at this public entry point. Specialist
`prepare_scheme_dependencies` defaults to downloads; `download=False` is required
when using it for a preview.

## Inspect results

`dataset.components[name]` holds a sequence of `PopulationResult` values. Inspect
each population's `qa`, and every member's `remap`, `qa`, `convergence`, and
`interpolation_provenance`. Each exposes `to_dict()` except provenance, which is
already a mapping. `population.save(directory, size_distribution=psd)` retains
detailed JSON diagnostics alongside validated NetCDF and CSV output.

The CLI build report includes `status`, `output`, `all_qa_passed` and dependency
information. It does not contain every member diagnostic. File validation checks
the saved schema and physical consistency; it does not establish suitability for
the research question. Some boundary products carry NaNs; inspect them explicitly.

Retain evaluated input JSON/PSD, version and import location, exact commands,
source manifest, RI table identities, reports and output paths. Include any
clipping, normalization, unperformed checks and unsupported boundaries in the
interpretation. Keep credentials outside the result bundle.
