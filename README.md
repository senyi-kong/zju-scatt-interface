# ZJU-SCATT Interface

<img src="docs/assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

Python and command-line tools for working with ZJU-SCATT single-particle and bulk
optical properties in atmospheric radiation, remote sensing, weather and climate
research. Find native data, select a physical population, calculate its optics,
and retain the inputs and provenance needed to reproduce the result.

The current version is **1.0.0** and requires **Python 3.9+**.
Use the documentation supplied with your release. Project resources:
[ZJU-SCATT homepage](https://zju_radiation.deep-time.org/)

## Contents

- [ZJU-SCATT Interface](#zju-scatt-interface)
  - [Contents](#contents)
  - [Features](#features)
  - [Supported particles](#supported-particles)
  - [Installation](#installation)
  - [Registration and setup](#registration-and-setup)
  - [Quick start](#quick-start)
    - [Preview and retrieve single-particle data](#preview-and-retrieve-single-particle-data)
    - [Build a bulk optical product](#build-a-bulk-optical-product)
  - [Examples](#examples)
  - [Outputs and reproducibility](#outputs-and-reproducibility)
  - [Scientific conventions](#scientific-conventions)
  - [Documentation and AI assistance](#documentation-and-ai-assistance)
  - [Project layout](#project-layout)
  - [Troubleshooting](#troubleshooting)
  - [Development and contributions](#development-and-contributions)
  - [Citation and license](#citation-and-license)

## Features

- Search the catalog, preview selections, download native files and reuse cached
  sources with explicit online/offline behavior.
- Interpolate supported wavelength, refractive-index, shape and environmental
  coordinates while retaining source-selection and interpolation provenance.
- Integrate analytical or supplied particle-size distributions (PSDs), calculate
  spectra, and combine explicitly weighted shape ensembles.
- Build separate reference-population tables or schemes retaining selected
  dimensions such as humidity, temperature and shape as output axes.
- Read, validate, export and plot scientific products through Python or the CLI.
- Export supported ARTS, CRTM and RTTOV layouts, including RTTOV14 lookup grids,
  and register custom particles, calculations, layouts or model handlers.

Source coverage and each export format's conventions still apply. File validation
checks the supported format contract; it does not establish acceptance by a
compiled radiative-transfer solver. See the
[scientific reference](docs/SCIENTIFIC_REFERENCE.md#7-downstream-model-formats).

## Supported particles

| Population | Built-in profile | Main selectable coordinates |
|---|---|---|
| Dust / generic super-spheroids | `super_spheroid` | Refractive index, roundness and aspect ratio |
| Black carbon | `encapsulated_fractal_aggregates_black_carbon` | Fractal dimension, coating fraction and RI scheme |
| Sea salt | `coated_super_spheroid_seasalt` | Relative humidity and branch |
| Ice | `super_spheroid_ice` | Temperature and paired shape coordinates |
| Sulfate | `sphere_sulfate` | Wavelength and available material/environment coordinates |
| Nitrate | `sphere_nitrate` | Wavelength and available material/environment coordinates |
| Organic carbon | `sphere_organic_carbon` | Wavelength and available material/environment coordinates |
| Water cloud | `sphere_water_cloud` | Wavelength and available material/environment coordinates |

Coordinates and coverage depend on the selected database version and native
sources. Use profile/schema inspection and selection reports before requesting a
large calculation. See the [user manual](docs/USER_MANUAL.md#1-capabilities-and-workflow).

## Installation

Python 3.9 or newer is required. Install from PyPI:

```console
pip install zju-scatt-interface
```

NumPy, h5py, netCDF4 and Matplotlib are installed automatically, along with their
dependencies. The CLI names `zju-scatt`, `zju-scatt-interface`, `zju_scatt` and
`zju_scatt_interface` all run the same tool. The Python import remains
`zju_scatt_interface`. To update an existing
installation, use `pip install --upgrade zju-scatt-interface`.

If you have already downloaded the source, run `pip install .` from the folder
containing `pyproject.toml`; use `pip install -e .` for editable development.

For raw-file retrieval without scientific dependencies:
`pip install --no-deps zju-scatt-interface`. This skips all runtime dependencies;
scientific operations need the omitted libraries, and `pip check` will report them
as missing. See the [installation guide](docs/USER_MANUAL.md#2-install-and-verify).

## Registration and setup

```console
python -m zju_scatt_interface --help
python -m zju_scatt_interface doctor --offline --json
zju-scatt register
zju-scatt doctor
```

Register once using your own information and consent. The saved local session is
reused across runs. Normal operations, including schema inspection and offline
calculations, require registration. Help and diagnostics are available beforehand.
Keep session tokens outside scripts, chat, version control and result bundles.
See [registration](docs/USER_MANUAL.md#3-registration) for available methods.

## Quick start

### Preview and retrieve single-particle data

The examples supply editable configurations with declared units and output paths.
Start with a small selection preview:

```console
python examples/research_workflows/03_download_seasalt_1p5um.py --help
python examples/research_workflows/03_download_seasalt_1p5um.py --list-only
```

Review the selected sources and estimated scope, edit
[03_retrieval_config.py](examples/research_workflows/03_retrieval_config.py), then run:

```console
python examples/research_workflows/03_download_seasalt_1p5um.py
```

A selection preview may contact the catalog and write reports; it does not download
optical files. Ordinary retrieval can download substantial data. In Python, the
corresponding entry point is `zsi.retrieve(config)`. See the
[retrieval walkthrough](docs/USER_MANUAL.md#5-retrieve-single-particle-data).

### Build a bulk optical product

Choose a recipe from [configs/recipes](configs/recipes), replace its demonstration
inputs with your scientific assumptions, and save your configuration as `scheme.json`.
Validate and inspect the plan before building:

```console
zju-scatt bulk-opt validate scheme.json --json --report validation.json
zju-scatt bulk-opt plan scheme.json --dry-run --json
zju-scatt bulk-opt plan scheme.json --workspace research_data --json
zju-scatt bulk-opt build scheme.json --workspace research_data --report build_report.json
```

The dry-run compiles queries locally. A normal plan can inspect the remote catalog
and write manifests but does not download optical files. The build resolves
sources and performs the calculation. Inspect coverage, QA and convergence reports
before interpreting the output.

The equivalent Python workflow is:

```python
import zju_scatt_interface as zsi

scheme = zsi.load_scheme("scheme.json")
queries = zsi.validate(scheme)
plan = zsi.plan(scheme, workspace="research_data")
dataset = zsi.build(scheme, plan=plan)
zsi.write(dataset, "product.nc")
zsi.validate("product.nc").require_valid()
```

For one PSD at one wavelength, use `zsi.compute_population(...)` with local sources.
For independent preset or measured-PSD spectra, use `zju_scatt_interface.bulk.build_table`.
See [your first scheme](docs/USER_MANUAL.md#4-your-first-bulk-scheme) and the
[function reference](docs/FUNCTION_REFERENCE.md) for complete inputs and return types.

## Examples

The [research workflow collection](examples/research_workflows/README.md) contains
**27 consecutively numbered drivers**, their configurations and eight synthetic
measured-format PSD inputs. It works with an installed interface; it does not
require the original local test folder.

| Release examples | Workflows |
|---|---|
| 01–10 | Database overview, native retrieval, species/environment selection and explicit RI inputs |
| 11–13 | One-population and paired-shape ensemble bulk calculations |
| 14–16 | Visible/IR reference tables and supplied measurement-format PSDs |
| 17–20 | RTTOV13, RTTOV14, CRTM IR and ARTS exports |
| 21–24 | RTTOV14 lookup grids, custom shapes, population codes and custom output layouts |
| 25–27 | Single-particle/bulk plotting and JSON-driven retrieval |

Start with `--help` and follow the collection's dependency order. The CSV inputs
are synthetic fixtures rather than observations. Generated data are kept under
`downloads/` beside the collection or an explicitly configured workspace.
The parent [examples folder](examples/README.md) contains a separate introductory
series with its own numbering.

## Outputs and reproducibility

Canonical scientific products include NetCDF data, configuration and provenance
metadata, source manifests, PSD definitions and machine-readable validation
reports. Selected workflows also write scalar/phase CSV files, HDF5 products,
figures or model-specific files.

Keep the configuration, interface version, selected native sources, RI tables,
shape weights, units and diagnostic reports with each scientific result. A cached
run is reproducible only when these inputs match. Use offline mode after the
required catalog/source dependencies have been cached; offline does not remove
the registration requirement. Reference-table checkpoints are keyed to scientific
inputs, source hashes and implementation identity.

See [inspection and output](docs/USER_MANUAL.md#9-inspect-save-and-plot) and
[reproducibility](docs/USER_MANUAL.md#12-troubleshooting-and-reproducibility).

## Scientific conventions

- PSD sizes are **radii**, with an explicit physical definition. Volume-equivalent
  radius and half maximum dimension are distinct coordinates.
- Scheme `dndr` values are **counts per represented bin in cm-3**, despite the
  historical name; convert differential measurement densities before use.
- Normalized wavelength is in **um**, temperature in **K**, and ordinary RH inputs
  are fractions. Model lookup APIs may explicitly use RH percent.
- Shape-ensemble entries represent paired coordinates and explicit weights.
  Preserve those pairs when selecting or interpolating sources.
- Coverage policies, finite-population normalization, RI schemes and phase
  normalization affect the physical meaning of a product and must be explicit.
- Execution success and physical closure do not establish numerical convergence.
  Inspect the reported diagnostics and source resolution for your population.

Consult the [scientific reference](docs/SCIENTIFIC_REFERENCE.md) for definitions,
interpolation rules, diagnostic interpretation and export limitations.

## Documentation and AI assistance

| Document | What it covers |
|---|---|
| [Documentation index](docs/README.md) | Where to start and the maintained documentation set |
| [User manual](docs/USER_MANUAL.md) | Installation through retrieval, PSDs, calculation, plotting and export |
| [Function reference](docs/FUNCTION_REFERENCE.md) | Each public function's purpose, inputs/defaults and outputs; types and methods |
| [Scientific reference](docs/SCIENTIFIC_REFERENCE.md) | Physical conventions, database assumptions and model formats |
| [Extension guide](docs/EXTENDING.md) | How extensions join the workflow, with contracts and a runnable PSD tutorial |
| [Research skill](docs/skills/zju-scatt-research/SKILL.md) | Instructions for an AI assistant working through the same public interface |

For AI-assisted work, provide the research skill, your scientific objective,
configuration and source constraints. Have the assistant inspect the actual API,
preview a plan, preserve units and assumptions, and return provenance and
validation evidence with the result. Review the physical assumptions yourself.
The skill uses the existing API and CLI; it requires no separate core interface.

## Project layout

```text
src/                      Python package and command-line implementation
configs/recipes/          Starting configurations for bulk workflows
examples/                 Introductory examples and research_workflows/
docs/                     Manual, API/scientific references and research skill
tests/                    Automated regression tests
```

## Troubleshooting

| Symptom | First check |
|---|---|
| Wrong command or missing API | Use `python -m zju_scatt_interface`; inspect the active environment and package path |
| Missing scientific dependency | Repeat the ordinary installation in the same Python environment to restore the default dependencies |
| Registration/session error | Run `zju-scatt doctor` and follow the registration instructions |
| Empty selection or boundary error | Check units, particle coordinates, RI scheme and native coverage; do not silently extrapolate |
| Offline file/catalog error | Populate the required dependencies online, then repeat with matching paths |
| QA or convergence warning | Inspect the per-population report, PSD coverage and native resolution before using the result |
| Model reader rejects an exported file | Check that model's supported layout, dimensions and normalization requirements |

For further diagnosis, retain the command, configuration, version and sanitized
error/report; omit credentials. See
[troubleshooting](docs/USER_MANUAL.md#12-troubleshooting-and-reproducibility) and the
[CLI overview](docs/USER_MANUAL.md#13-command-line-overview).

## Development and contributions

Install development extras, make a focused change, and run the relevant tests
from the project root. The full automated suite uses standard-library unittest:

```console
pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

For new particles or output handlers, start with the
[extension guide](docs/EXTENDING.md). Include reproducible input, expected behavior,
relevant tests and documentation with proposed changes. Report software problems
through the project's hosting platform or maintainer channel supplied with your
release. See [CHANGELOG.md](CHANGELOG.md) for recorded changes.

## Citation and license

If you use this interface in your research, please cite the following paper once
published:

> Senyi Kong and Lei Bi. *ZJU-SCATT Interface: a streamlined Python workflow from
> single scattering data to bulk aerosol and cloud optical properties*.
> **[Publication details and DOI to be added after publication.]**

This is a citation placeholder. Record the interface and database/source versions
used, and cite the underlying particle models and optical datasets as appropriate.

The interface code is distributed under the [MIT license](LICENSE), with author
Senyi Kong and maintenance by the ZJU-SCATT Team as recorded in `pyproject.toml`.
Consult the data service for terms governing the underlying optical datasets.
