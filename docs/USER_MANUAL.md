# ZJU-SCATT Interface user manual

<img src="assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

This manual takes you from installation to reproducible optical-property products.
The [function reference](FUNCTION_REFERENCE.md) gives exact Python signatures and
returns. The [scientific reference](SCIENTIFIC_REFERENCE.md) explains conventions
that affect the physical meaning of the calculation.

## Contents

1. [Capabilities and workflow](#1-capabilities-and-workflow)
2. [Install and verify](#2-install-and-verify)
3. [Registration](#3-registration)
4. [Your first bulk scheme](#4-your-first-bulk-scheme)
5. [Retrieve single-particle data](#5-retrieve-single-particle-data)
6. [Prepare a size distribution](#6-prepare-a-size-distribution)
7. [Calculate and combine populations](#7-calculate-and-combine-populations)
8. [Build spectra, tables and retained grids](#8-build-spectra-tables-and-retained-grids)
9. [Inspect, save and plot](#9-inspect-save-and-plot)
10. [Customize and export](#10-customize-and-export)
11. [Use AI assistance](#11-use-ai-assistance)
12. [Troubleshooting and reproducibility](#12-troubleshooting-and-reproducibility)
13. [Command-line overview](#13-command-line-overview)
14. [Migrate existing scripts](#14-migrate-existing-scripts)

## 1. Capabilities and workflow

The interface supports eight built-in particle profiles: dust/generic
super-spheroids, black carbon, sea salt, ice, sulfate, nitrate, organic carbon, and
water cloud. It resolves native sources, uses a verified cache, interpolates
supported coordinates, integrates particle-size distributions (PSDs), averages
specified ensembles, and writes scientific outputs. Registered extensions can add
other implementations without changing the root API.

Choose the smallest workflow that answers your question:

| Goal | Workflow |
|---|---|
| Obtain single-particle optical files | Configured `retrieve` |
| Integrate one PSD at one wavelength | `compute_population` with local sources |
| Calculate spectra or several named populations | `load_scheme` → `validate` → `plan` → `build` |
| Build reference spectra with explicit presets | `bulk.build_table` |
| Keep temperature/RH/shape values as output axes | Retained grid schemes |
| Inspect existing products | `read`, `validate` and `plot` |
| Prepare an application-specific input | Canonical output followed by a supported exporter |

Use the compact root API for ordinary work:

```python
import zju_scatt_interface as zsi
```

Public namespaces such as `zju_scatt_interface.psd` and
`zju_scatt_interface.bulk` expose specialist types and functions. Do not import
underscore-prefixed numerical kernels in research scripts.

The [research workflow examples](../examples/research_workflows/README.md) provide
complete numbered drivers, editable configurations and synthetic measured-format
PSD inputs for the workflows in this manual.

## 2. Install and verify

Python 3.9 or newer is required. Install the latest compatible release from PyPI:

```console
pip install zju-scatt-interface
```

NumPy (`>=1.23`), h5py (`>=3.9`), netCDF4 (`>=1.6`) and Matplotlib (`>=3.7`)
are installed automatically, with their dependencies. No scientific extra is
needed. To update an existing installation, use
`pip install --upgrade zju-scatt-interface`. The distribution provides four
equivalent commands: `zju-scatt`, `zju-scatt-interface`, `zju_scatt` and
`zju_scatt_interface`. They all call the same CLI implementation.

If you have already downloaded the source code, run `pip install .` from the
folder containing `pyproject.toml`. For editable development use `pip install -e .`,
or `pip install -e ".[dev]"` to include development tools. The source files are
located directly under `src/`; installed imports remain `zju_scatt_interface`.

For standard-library registration, catalog queries and raw-file downloads only,
use `pip install --no-deps zju-scatt-interface`. This skips all runtime dependencies
rather than installing a separately packaged base edition; it does not remove
existing libraries. Scientific PSDs, interpolation/integration, derived retrieval
products, NetCDF/HDF5 I/O and plotting need their scientific dependencies.
For source-only retrieval use `access.retrieve_sources(..., apply_interpolation=False)`;
see [lower-level source selection](#lower-level-source-selection).

`pip check` reports required libraries intentionally omitted by `--no-deps`.
Repeating an ordinary `pip install zju-scatt-interface` installs missing declared
requirements. For a source checkout, `pip install --no-deps .` is the equivalent
opt-out; build requirements still apply. The older `[all]`, `[native]`, `[netcdf]`
and `[plot]` extras remain compatible but are no longer needed for a full install.

Check that Python and the command refer to the intended installation:

```console
python -c "import zju_scatt_interface as zsi; print(zsi.__version__); print(zsi.__file__)"
python -m zju_scatt_interface doctor --offline --json
```

`python -m zju_scatt_interface` can replace any of those commands. CLI aliases
do not add Python import packages: use `import zju_scatt_interface`, or
`import zju_scatt_interface as zju_scatt` to give it a shorter local name.

Offline diagnostics do not contact the service. They report missing registration
or dependencies as incomplete setup, with a nonzero exit status when required
checks fail. Online `zju-scatt doctor` also checks connectivity/session validity.

## 3. Registration

Register once for the current OS account:

```console
zju-scatt register
zju-scatt doctor
```

The existing session is reused across runs and virtual environments through
`~/.zju_scatt/session.json`. Registration is required for normal Python and CLI
operations, including local validation, schema discovery, plotting and offline
calculations. Help, diagnostics and registration/session management remain
available before registration. `--no-track` disables tracking where supported; it
does not bypass registration.

Use the browser-assisted method if necessary:

```console
zju-scatt register --method browser
```

Follow the local terminal instructions. Keep tokens out of chat, source files,
shell history, screenshots and shared reports. Researchers must supply their own
identity information and consent. If an existing session is rejected, follow the
displayed session-management instructions rather than creating repeated registrations.

## 4. Your first bulk scheme

A scheme describes wavelengths, separately named particle populations, their PSDs,
scientific parameters, calculation policies and output. JSON is portable and
contains data only. Python configurations execute code and should be trusted.

### 4.1 Start with a complete recipe

The source distribution includes these schema `1.0` examples:

| Recipe in `configs/recipes/` | Demonstrates |
|---|---|
| `dust_bulk.json` | Fixed-index dust and joint shape members |
| `black_carbon_bulk.json` | Core/coating indices, size units and joint BC geometry |
| `sea_salt_bulk.json` | Database-derived RI, fractional RH and humidity branch |
| `ice_multi_temperature_bulk.json` | Wavenumber conversion and three independent temperatures |

Copy the closest recipe to a new experiment directory. Its numbers and policies,
including any truncation setting, are examples. Replace them with inputs justified
for your application. Do not silently treat a recipe PSD as a measured population.

For a small inspectable starting point, save the following as `scheme.json`.
It is a demonstration of the configuration structure; source availability and
physical size coverage must still be checked during execution:

```json
{
  "schema_version": "1.0",
  "name": "ice_demo",
  "wavelength_unit": "um",
  "wavelengths": [1.6],
  "particles": [
    {
      "name": "ice",
      "particle_type": "super_spheroid_ice",
      "size_distribution": {
        "size": [5, 10, 20, 40, 80, 150],
        "dndr": [5, 30, 100, 80, 20, 2],
        "size_unit": "um",
        "size_definition": "volume_equivalent_sphere_radius"
      },
      "refractive_index": {
        "mode": "database_temperature",
        "temperature_k": 250
      },
      "shape_parameters": {"roundness": 2.1, "aspect_ratio": 1.7}
    }
  ],
  "calculation": {
    "truncation_policy": "error",
    "check_convergence": true,
    "strict_convergence": true,
    "strict_qa": true
  },
  "output": {"path": "products/ice_demo.nc", "format": "netcdf4"}
}
```

The PSD contains represented-bin concentrations: its sum is `237 cm-3`.
It does not contain a continuous `dN/dr`. This example deliberately rejects
uncovered PSD bins and failed convergence rather than adjusting the population.

### 4.2 Discover and validate

Inspect supported parameters in the installed version:

```console
zju-scatt describe super_spheroid_ice --json
zju-scatt bulk-opt schema --particle-type super_spheroid_ice --json
zju-scatt bulk-opt validate scheme.json --json --report validation.json
```

The machine reference documents names, roles and ranges. It is not a generic
JSON Schema and does not prove that all coordinate combinations exist. The
validation command normalizes the scheme and checks particle-specific inputs.

### 4.3 Preview the work

```console
zju-scatt bulk-opt plan scheme.json --dry-run --json --report query_preview.json
zju-scatt bulk-opt plan scheme.json --workspace research_data --json --report dependency_plan.json
```

These operations have different meanings:

| Operation | What happens | What remains unchecked |
|---|---|---|
| `validate` on JSON | Local normalization/parameter checks; optional report | Actual sources and numerical result |
| `plan --dry-run` | Local dependency-query compilation; no workspace creation | Remote availability, cached readiness, common size coverage |
| Normal `plan` | May scan the catalog and write workspace/manifests; no optical downloads | A complete numerical calculation |
| `plan --offline` | Checks a saved dependency manifest and local cache | Data absent from that cache |

An explicit `--report` writes a file even for a dry-run. Check the command's exit
code and report before continuing. A normal plan may return `incomplete` and exit
`2` because selected sources are not cached. An online build can obtain missing
downloads; it cannot repair an invalid scientific request. A plan with explicit
local `--source` overrides records paths without proving source validity/coverage.

### 4.4 Build and review

```console
zju-scatt bulk-opt build scheme.json --workspace research_data --report build_report.json
```

An online build prepares missing dependencies, interpolates, integrates, runs
the configured checks and writes the selected output. Use the report's `output`
path; relative scheme outputs are placed under the workspace in this CLI workflow.
To specify a destination directly, use the build command's `--output` option.

Input/validation exceptions may occur before a report is written. Inspect stderr
and exit status as well as the report. In PowerShell use `$LASTEXITCODE`; in scripts
check the subprocess return code.

Inspect the generated file and plot it:

```python
import zju_scatt_interface as zsi

output = "research_data/products/ice_demo.nc"
zsi.validate(output).require_valid()
content = zsi.read(output)
print(content["components"]["ice"]["datasets"]["beta_ext"]["data"])
zsi.plot(output, kind="bulk")
```

File validation checks the stored product. It does not establish that the input
assumptions or numerical resolution are adequate for every research application.
Section 9 explains the separate scientific diagnostics.

## 5. Retrieve single-particle data

Use configured `retrieve` to obtain optical sources or derived single-particle
products without integrating a PSD:

```python
import zju_scatt_interface as zsi

request = {
    "particle_types": "ice",
    "target_wavelengths": [1.6],
    "target_temperatures": [250],
    "shapes": {"n": 2.1, "asp": 1.7},
    "output_dir": "downloads/ice"
}
preview = zsi.retrieve(request, download=False)
run = zsi.retrieve(request)
result = run.single
for product in result.interpolated_products:
    print(product.path)
```

The preview can query remote listings but does not download optical files. Normal
configured retrieval downloads and, when required, interpolates by default. It
checks completion and writes standard manifests/reports. Requests lacking shape
constraints can select many files; inspect the preview first.

Save the mapping as JSON or as a trusted Python file defining `retrieval`, then
pass its path to `retrieve`. The CLI equivalent is:

```console
python -m zju_scatt_interface retrieve --config input.py
```

Relative paths in a configuration file resolve beside that file. An in-memory
mapping resolves paths from the working directory. Python retrieval files execute
code; JSON files contain data only.

### Batch retrieval

```python
requests = {
    "target_wavelengths": [1.5],
    "output_dir": "downloads/multi",
    "requests": {
        "dust": {"shapes": {"n": 2.1, "asp": 1.7}},
        "black_carbon": {"shapes": {"df": 1.8}},
        "sea_salt": {}
    }
}
```

Use `zsi.retrieve(requests)`. Inspect `run.results[name]` and the root
`retrieval_report.json`. All jobs are attempted; a failed batch raises
`RetrievalRunError`, whose `result` retains completed/failed jobs. The complete
report records resolved RI tables, selected source keys and interpolation products.
`requests="all"` expands registered species; it is a broad request, not an
assumption that every species is available or scientifically appropriate.

### Lower-level source selection

Use `access.retrieve_sources` when you need raw selected objects and explicit
download/interpolation controls:

```python
from zju_scatt_interface.access import retrieve_sources

selected = retrieve_sources(
    particle_types="dust",
    target_wavelengths=[1.6],
    shapes={"n": 2.1, "asp": 1.7},
    download=False,
)
print(selected.total_bytes)
```

Unlike configured retrieval, the raw selector's defaults do not apply the same
completion requirements. Check its status and use `raise_for_status` with the
required download/match/product checks before consuming it.

`shapes` supports exact scalars, inclusive two-number Python tuples, and lists of
paired mappings. A list of mappings preserves the listed combinations. A tuple
range is Python-specific; do not assume a JSON list has identical range semantics.
Partial mappings leave other axes unrestricted. Complete scalar shapes can become
interpolation targets in supported wavelength/temperature retrieval workflows;
raw filtering and range selection retain their documented selection behavior.

The low-level parameters `apply_interpolation=False` and
`interpolation_output_dir=...` control derived products. Source files used for a
later bulk calculation can be downloaded without an intermediate derived file.
Automatic retrieval preserves native variable names, units, dimensions, phase
representation and metadata; native `cext` may still be dimensionless `Cext*k²`.

## 6. Prepare a size distribution

### Discrete measured populations

```python
from zju_scatt_interface import SizeDistribution

psd = SizeDistribution(
    size=[0.05, 0.10, 0.20, 0.40],
    dndr=[10, 40, 35, 15],
    size_unit="um",
    size_definition="volume_equivalent_sphere_radius",
)
psd.to_csv("psd.csv")
restored = SizeDistribution.from_file("psd.csv")
```

Here `size` is a radius coordinate; `dndr` is the number concentration in each
represented bin, in `cm-3`. The represented concentration is `sum(dndr)`.
Observed differential densities must first be integrated over their actual
measurement bins. Do not infer widths, logarithm base or particle geometry from
column names alone. See [PSD conventions](SCIENTIFIC_REFERENCE.md#2-size-distributions).

CSV, NetCDF and HDF5 input helpers allow explicit column/variable names and units.
Use `from_delimited`, `from_netcdf` or `from_hdf5` when automatic file loading is
insufficient. Size definitions are independent per population. Converting between
volume-equivalent and maximum-dimension radius requires verified geometry.

### Analytical populations

```python
from zju_scatt_interface.psd import lognormal_psd, gamma_psd

aerosol = lognormal_psd(
    rg_um=0.7, sigma_g=1.8, number_concentration_cm3=10,
    bins=400, normalization="preserve",
)
cloud = gamma_psd(
    effective_radius_um=10, effective_variance=0.1,
    number_concentration_cm3=1, bins=400,
)
```

The factories integrate finite bins and return `SizeDistribution` objects on a
volume-equivalent-radius grid. `rg_um` is a geometric mean radius, not diameter.
Gamma effective radius is `M3/M2` on that radius definition. Explicit
`radius_range_um` sets finite bounds. `normalization="preserve"` retains the
parent probability inside those bounds; `"renormalize"` scales the finite
representation to the supplied concentration. Metadata record omitted probability
and realized moments. Measured PSDs are not automatically normalized.

Functions or instrument preprocessing can supply evaluated arrays to the same
constructor. `from_callable` evaluates a function at size coordinates according
to the discrete-bin contract; it does not infer that the function is a continuous
differential density requiring integration.

## 7. Calculate and combine populations

### One population at one wavelength

The following example assumes `sulfate_sources` points to appropriate local native
files and `psd` is already prepared:

```python
import zju_scatt_interface as zsi

result = zsi.compute_population(
    "sphere_sulfate", sulfate_sources, psd,
    wavelength=0.55,
    parameters={"relative_humidity": 0.8},
    truncation_policy="error",
    check_convergence=True,
    strict_qa=True,
)
print(result.bulk.extinction_coefficient)
print(result.bulk.single_scattering_albedo)
print(result.qa.to_dict())
result.save("results/sulfate", size_distribution=psd)
```

The workflow validates the profile, resolves native sources, interpolates optical
properties, checks common physical size coverage, conservatively remaps the PSD,
integrates physical cross sections, combines declared members, and computes QA
and convergence reports. Bulk coefficients are `m-1`.

For direct work with a loaded slice, use `optics.load_single`, then
`zsi.integrate(optics, psd)`. The latter returns `(BulkOptics, RemapReport)`.
Use the loaded physical cross sections rather than interpreting native dimensionless
`cext` externally without its scaling convention.

### Joint shapes and independent parameters

```python
from zju_scatt_interface.bulk import WeightedShapeEnsemble

ensemble = WeightedShapeEnsemble.from_shapes(
    [{"roundness": 2.0, "aspect_ratio": 1.0},
     {"roundness": 2.5, "aspect_ratio": 1.5}],
    weights=[0.4, 0.6],
)
```

Pass this as `shape_ensemble=ensemble` to a supported population calculation.
`WeightedValues` instead expresses an independently varying coordinate, such as
RH values with population weights. Independent weighted coordinates form a
Cartesian product; joint shape members preserve the given pairs. Weights must be
finite, nonnegative and have a positive sum. A coordinate must not be declared in
both an independent weighted parameter and a joint member.

`zsi.combine(results, weights)` combines extensive coefficients and derives SSA,
asymmetry and phase quantities using the appropriate scattering weights. Specify
what the weights represent; do not arithmetic-average derived optical quantities.
Scheme components are stored separately, without an implicit mixture.

### Coverage and policies

`truncation_policy="error"` rejects uncovered PSD concentration.
`"truncate"` is an explicit alternative that uses common physical size coverage
across members and records losses. It does not silently restore lost concentration.
Inspect `member.remap`, size-coverage metadata and convergence before interpreting
a truncated result. Do not switch policy only to suppress a failure.

## 8. Build spectra, tables and retained grids

### Typed multi-population scheme

```python
import zju_scatt_interface as zsi
from zju_scatt_interface.config import IceComponent, SchemeOutput

ice = IceComponent(
    "ice_250k", temperature_k=250,
    size=[5, 10, 20, 40, 80, 150],
    dndr=[5, 30, 100, 80, 20, 2],
    roundness=2.1, aspect_ratio=1.7,
)
scheme = zsi.Scheme(
    name="ice_spectrum", wavelengths_um=(0.55, 0.67, 1.6),
    particles=(ice,),
    output_settings=SchemeOutput("ice_spectrum.nc", "netcdf4"),
)
scheme.write_json("normalized_scheme.json")
queries = zsi.validate(scheme)
dependencies = zsi.plan(scheme, workspace="research_data")
dataset = zsi.build(scheme, plan=dependencies)
zsi.write(dataset, "ice_spectrum.nc")
```

Unlike CLI `bulk-opt build`, the high-level Python `build` returns a dataset;
call `write` to save it. An incomplete plan is refreshed in the same workspace,
inheriting its offline policy. Use `plan=`, not `dependency_plan=`, at the public
entry point. Retained grid schemes instead require explicit local source paths.

Add separately named components to calculate several populations. Repeated
temperatures can be represented by repeated named components, as in the ice
recipe. They are independent results, not an automatic temperature average.

### Cache and offline work

The dependency workspace contains `cache/`, `work/` and `manifests/`. Source
manifests record the scheme/query identities, source keys, available remote
checks, local hashes, validation issues and readiness. Reuse is based on verified
source information, not filename presence alone.

```console
zju-scatt bulk-opt plan scheme.json --workspace research_data --offline --json
zju-scatt bulk-opt build scheme.json --workspace research_data --offline --report offline_build.json
```

Offline automatic builds need the matching saved manifest and verified cached
sources. Changed scientific inputs can change dependency identities. If the
cache is incomplete, obtain the sources during a separately authorized online
preparation or provide explicit local sources. CLI `--source COMPONENT=PATH`
overrides must cover every component; partial local/automatic mixing is rejected.

`scheme-sources` prepares/downloads dependencies without building optics. The
specialist `sources.prepare_scheme_dependencies` also defaults to downloads;
pass `download=False` for inspection. Ordinary `zsi.plan` never downloads optical data.

### Reference spectral tables

```python
from zju_scatt_interface.bulk import build_table

table = build_table({
    "species": ["dust", "ice"],
    "wavelengths": [0.55, 0.67, 1.6],
    "preset": "literature_v1",
    "number_concentration_cm3": 1.0,
    "workspace": "table_cache",
    "output_dir": "table_results",
    "formats": ["nc", "csv"],
    "include_phase_matrix": False,
    "overrides": {},
})
assumptions = table.report
rows = table.rows
```

This workflow uses explicit reference shapes, environment, RI and PSD assumptions.
`literature_v1` is a reference preset, not a sample-specific measurement or a
universal climatology. `reference_v1` retains earlier illustrative settings.
Inspect the resolved assumptions, clipping/normalization, realized moments and
common physical coverage. See [presets](SCIENTIFIC_REFERENCE.md#5-reference-presets).
Use `bulk.resolve_bulk_settings` to inspect preset/override settings without a
download or calculation. Trusted Python input files define `bulk_table`; JSON
and `BulkTableConfig` objects are also accepted.

### Retained multidimensional grids

Retained grids preserve temperature, RH, wavelength or geometry as output axes.
They do not average those coordinates. PSD size bins remain integrated quantities,
not retained optical-grid axes.

```python
import zju_scatt_interface as zsi
from zju_scatt_interface.bulk import load_grid_scheme

grid_scheme = load_grid_scheme("configs/multidimensional_bulk_scheme.example.py")
grids = zsi.build(
    grid_scheme,
    source_paths={"ice": ice_sources, "sulfate": sulfate_sources},
)
zsi.write(grids, "bulk_grids.nc")
```

Supply native local sources for the named particle grids. Each particle can have
its own declared dimensions. Every single-particle grid includes a positive
wavelength axis in `um`; expansion follows declared order, with the last axis
varying fastest. Weighted ensembles and retained axes represent different scientific
operations. Use the example configuration as a structural guide and replace its
assumptions deliberately.

## 9. Inspect, save and plot

### Keep diagnostic evidence

`dataset.components[name]` contains a sequence of `PopulationResult` values:

```python
for name, populations in dataset.components.items():
    for population in populations:
        print(name, population.wavelength_um, population.qa.to_dict())
        for member in population.members:
            print(member.qa.to_dict())
            print(member.convergence.to_dict())
            print(member.remap.to_dict())
            print(member.interpolation_provenance)
```

The CLI build report includes `all_qa_passed` but does not serialize every member
diagnostic. Retain Python results or `PopulationResult.save` summaries when
convergence/remapping details matter. A disabled check is unchecked, not passed.
Boundary policies can produce NaN optical arrays with warnings/provenance; a
written file is not proof of supported physical values.

### Save and reopen

```python
import zju_scatt_interface as zsi

zsi.write(dataset, "product.nc")
zsi.write(dataset, "product.h5")
zsi.validate("product.nc").require_valid()
content = zsi.read("product.h5")
```

The format is inferred from the suffix or selected by `format="netcdf4"`/
`"hdf5"`. `read` returns an inspection mapping, not reconstructed calculation
objects. A bare `BulkOptics` requires `wavelength_um`; a homogeneous sequence of
bare optics requires `wavelengths_um`. Population/dataset results carry theirs.

`PopulationResult.save(directory, size_distribution=psd)` writes a validated
NetCDF product, scalar/phase CSV when available, the supplied PSD and a JSON
summary. `include_members=True` retains member rows. The opt-in `l2_lognormal`
mode is a separate normalized dust L2 export with stricter input requirements;
it does not change the concentration of the ordinary application output.

Canonical writes use atomic replacement after validation. An existing destination
can therefore be replaced by a successful write; choose a new experiment path if
the previous result must be preserved. Use `OutputOptions` for compression,
chunking and atomic controls.

### Plot existing data

```console
zju-scatt plot single_scattering.nc
zju-scatt plot bulk_optics.nc
```

The CLI detects the product kind; `--kind single` or `--kind bulk` overrides
ambiguous detection. Python file plots require an explicit kind:

```python
import zju_scatt_interface as zsi

single = zsi.plot("single_scattering.nc", kind="single")
bulk = zsi.plot("bulk_optics.nc", kind="bulk")
```

Single-particle inspection saves figures, CSV values and an inspection report.
Use `wavelength_um` and `coordinate_indices` to select a needed native slice.
Bulk plots preserve dimensions: scalar plots vary an available axis, other axes
are fixed and labeled, and phase plots select representative curves. Inspect the
selection report; plotting does not recalculate or average the data.
For live single-particle figures use `plotting.plot_single_particle_optics` on a
loaded `SingleParticleOptics`; `OpticalPlotStyle` controls fonts and styling.

## 10. Customize and export

### Custom NetCDF/HDF5 layouts

Use `io.export_bulk_optics` to select species, groups, variables, coordinates,
unit conversions and data types from a canonical product:

```python
from zju_scatt_interface.io import export_bulk_optics

layout = {
    "format": "netcdf4",
    "filename": "custom_optics.nc",
    "group": "Optics/{species}",
    "variables": {
        "extinction": {"source": "beta_ext", "units": "km^-1"},
        "albedo": {"source": "ssa", "units": "1"},
        "asymmetry": {"source": "g", "units": "1"}
    }
}
written = export_bulk_optics("product.nc", layout, output_dir="exports")
```

Layouts can be mappings, JSON, or trusted Python specifications defining `output`
or `outputs`. Relative output locations resolve beside a configuration file unless
`output_dir` is provided. Existing exports require `overwrite=True`. The canonical
source must not be overwritten. Multi-file export validates layouts before writing,
but an I/O failure can still leave some completed files.

Variables keep their actual axes. Requesting an RH or size coordinate cannot
create a physically absent axis. Supported unit conversions are explicit;
mass-normalized optics require mass concentration, not just a new unit label.
Custom layout output is not automatically a model-native format.

### Custom text tables

```python
from zju_scatt_interface.io import load_optical_table_format, write_formatted_optical_output

spec = load_optical_table_format("configs/optical_table_format.example.py")
paths = write_formatted_optical_output("model_optics.dat", "product.nc", spec)
```

The format specifies column fields, labels, units, scaling, delimiters and headers.
Text-table conversion is controlled explicitly by scale/transform settings; do not
expect a unit label alone to convert a value. Supported Python specs can define
filters/transforms; review them as executable code. Match the exact downstream
reader, including required sentinels and phase/coordinate ordering.

### Application exporters and native templates

Use `io.applications` exporters for supported ARTS, CRTM IR, RTTOV13 and RTTOV14
workflows. Each has separate concentration, phase and axis requirements. A
registered exporter can also be called with `extensions.export(application, ...)`.
See [model formats](SCIENTIFIC_REFERENCE.md#7-downstream-model-formats) before use.

RTTOV14 retained lookup tables can preserve effective radius, RH and ice
temperature. The master cube may require exact-node slicing or a reader adapter
for stock runtime axes; it is not an interchangeable fixed-population table.
Model validators check implemented structures, not universal acceptance by every
compiled model release. In particular, high-level RTTOV13 descriptive/ZJU cloud
names require reader changes, and the CRTM IR exporter covers a subset.

The supplementary `io.native` functions provide templates, explicit arrays,
reference-file inspection and independent serialization. Use them when you have
the full required model arrays and an exact target contract. They do not invent
uncomputed categories, sizes, temperatures or microwave properties.

## 11. Use AI assistance

The [research skill](skills/zju-scatt-research/SKILL.md) teaches an assistant to
use this interface. Supply it directly to an assistant with filesystem access, or
copy the entire `docs/skills/zju-scatt-research` folder to the client's local skill
directory. Keep the matching source manual/reference available and tell the
assistant the project location; a Python wheel need not install Markdown files.

A useful task includes the particle, spectrum and units, PSD convention/size
definition, shape/environment, RI strategy, desired output and permitted online
work. For example:

> Use the ZJU-SCATT research skill and the installed interface. Prepare an ice
> calculation at 1.6 um and 250 K with roundness 2.1 and aspect ratio 1.7. Read my
> measured radius-bin counts in cm-3, preserving the volume-equivalent radius
> definition. Validate and preview first. Report missing choices, source coverage,
> QA and convergence; retain evaluated inputs and provenance with the output.

An assistant should discover the installed contract, resolve missing physical
choices, prepare data-only inputs where possible, validate, preview, execute within
the requested scope and inspect diagnostics. Demonstration values are not a
substitute for missing measurements. Do not supply registration tokens to the AI.

Assess its behavior with both successful and incomplete requests:

| Scenario | Expected behavior |
|---|---|
| No PSD or shapes supplied | Asks for consequential choices, continues independent setup checks |
| Differential PSD without bin widths/convention | Requests the missing measurement definition |
| Correlated shape pairs | Keeps paired members rather than creating all combinations |
| Offline cache incomplete | Reports missing dependencies and remains offline |
| Unsupported target/boundary NaNs | Reports the unsupported region without extrapolation or replacing NaNs |
| PSD beyond common coverage | Reports the problem; truncates only when deliberately selected |
| File generated with disabled convergence | Reports convergence as unchecked |
| Old API example with the same version number | Checks actual imports/commands and migrates explicitly |

Evaluate scientific meaning and reproducibility, not merely whether generated
code exits successfully. Local schema/dry-run checks do not replace numerical
validation with representative source data.

## 12. Troubleshooting and reproducibility

| Symptom | Check and action |
|---|---|
| Import or command missing | Confirm interpreter/import location; install from the project root; use `python -m zju_scatt_interface` |
| Registration required | Complete one-time registration locally; reuse the existing session |
| Missing scientific library | Run the ordinary installation in the same Python environment to restore default requirements |
| Required/forbidden coordinate | Inspect `describe PARTICLE_TYPE --json` and `bulk-opt schema` |
| RH rejected | Supply a fraction such as `0.8`; the RTTOV lookup API's explicit percent field is a separate export contract |
| Invalid size coverage | Check units, radius definition and bin support; inspect common coverage before deciding on truncation |
| Unsupported interpolation | Obtain supported sources or revise the scientific request; use nearest selection only when intended |
| RI table missing | Verify the supported material table or supply justified in-range explicit indices |
| Plan incomplete | Distinguish uncached sources, invalid source files and unsupported scientific coordinates |
| Offline manifest missing | Use the matching prepared workspace or explicit local component sources |
| Build completed but uncertain result | Inspect NaNs, member QA, convergence, remapping, phase resolution and defaults |
| Export rejected | Check exact model/version, phase representation, axes and required number/mass concentration |

Distinguish four conclusions: valid configuration, ready source dependencies,
completed execution, and scientific adequacy. None automatically establishes the
next. Keep the evaluated configuration/PSD, package version and import location,
commands, resolved presets/RI tables, source identities/hashes where available,
reports and output paths. Record clipping, normalization, unchecked diagnostics,
plot coordinate selections and limitations. Keep session files outside shared bundles.

## 13. Command-line overview

Run `zju-scatt COMMAND --help` for the installed options. Commands include:

| Group | Commands | Purpose |
|---|---|---|
| Setup | `register`, `session`, `doctor` | Onboarding, session management and diagnostics |
| Discovery | `browse`, `list`, `search`, `estimate`, `describe`, `metadata` | Inspect remote objects and particle metadata |
| Sources | `retrieve`, `download`, `check` | Configured/raw retrieval, transfer and checks |
| Bulk inputs | `scheme`, `psd-check`, `resolve-ri` | Inspect scheme, PSD and optical-constant inputs |
| Dependencies | `scheme-sources` | Prepare/verify source manifests and cache; can download |
| Bulk workflow | `bulk-opt schema`, `validate`, `plan`, `build` | Machine reference and staged scheme execution |
| Table integration | `bulk` | Integrate explicitly supplied tabular single-particle quantities |
| Inspection | `plot` | Plot obtained single/bulk products |

Extension commands appear after their modules are explicitly imported by the host
application. Do not infer a CLI flag from a Python keyword; inspect command help.

## 14. Migrate existing scripts

The domain reorganization removes earlier flat module paths and writer aliases.
File schemas and scientific conventions are not changed merely by renaming an API.

| Previous name | Current entry point |
|---|---|
| `BulkSchemeConfig`, `BulkOpticalScheme` | `config.Scheme` |
| `BulkOpticalResult` | `optics.BulkOptics` |
| `BulkCalculationResult` | `bulk.PopulationResult` |
| `BulkSchemeBuildResult` | `bulk.BulkDataset` |
| `SourceDependencyPlan` | `sources.DependencyPlan` |
| `run_retrieval` | Root `retrieve` |
| `retrieve_data` | `access.retrieve_sources` |
| `calculate_bulk_optics` | Root `compute_population` |
| `load_single_particle_optics` | `optics.load_single` |
| `build_bulk_scheme` | Root `build` or specialist `bulk.build_dataset` |
| `run_bulk_table` | `bulk.build_table` |
| Format-specific canonical writers | Root `write(product, path, format=...)` |
| Root plotting helpers | Root `plot`, or specialist functions under `plotting` |

At the public `build` entry point use `plan=`. The specialist `build_dataset`
still has `dependency_plan=`; do not transfer keyword names between the two.
The [function reference](FUNCTION_REFERENCE.md) documents available exported
callables and identifies unresolved advertised exports in the current source.
