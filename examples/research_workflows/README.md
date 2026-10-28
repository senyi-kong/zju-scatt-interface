# Research workflow examples

<img src="../../docs/assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

This collection contains the 27 production examples promoted from the verified
local user tests, numbered consecutively from 01 to 27. Original maintenance
examples 05, 06 and 07 were excluded before renumbering; original 08–30 now
correspond to release examples 05–27.
The existing examples in the parent folder are a separate collection.

Install the interface in your chosen Python environment, then complete registration
once. Scientific dependencies are included by default. An editable install is optional
for this collection.
After installation, run the example commands from a downloaded source checkout:

```console
pip install zju-scatt-interface
python -m zju_scatt_interface register
python examples/research_workflows/local_environment.py
python examples/research_workflows/01_database_overview.py --offline
```

Use `python SCRIPT --help` for supported options. On Linux/macOS/WSL, the optional
`run_local.sh` wrapper uses the active `python` (or the `PYTHON` environment variable).
No `.venv`, editable-install metadata, local source mount or original test folder
is required. Windows users can call the same Python scripts directly.

## Reading and running the collection

| Examples | Purpose | Inputs and dependencies |
|---|---|---|
| 01 | Registry/RI and database overview | `--offline` is registry-only; default also lists the service |
| 02 | Native sea-salt files across 0.3–1.0 um | `02_retrieval_config.py` |
| 03 | Sea salt at 1.5 um | `03_retrieval_config.py` |
| 04 | Dust, BC and sea salt at 1.5 um | `04_retrieval_config.py`; broad shape coverage can require GB of data |
| 05, 06 | All registered species at 1.5/1.6 um | Matching retrieval configs; per-species shape/environment overrides |
| 07 | Ice at 250 K and 1.6 um | `07_retrieval_config.py` |
| 08 | Ice at interpolated shape n=2.1, asp=1.7 | `08_retrieval_config.py`; useful input for 25 |
| 09 | Dust at explicit refractive index | `09_retrieval_config.py`; no physical wavelength is assigned |
| 10 | Dust and BC at complete explicit indices | `10_retrieval_config.py`; dimensionless native products |
| 11 | One-shape lognormal dust population | Shared `ensemble_bulk_config.py`; application N=10 and an explicit N=1 L2 export |
| 12 | Three paired native dust shapes | Same shared config; per-shape integration before averaging, with member/L2 reports |
| 13 | Interpolated dust shape ensemble | Same shared config; source/shape provenance retained |
| 14 | All-species scalar table over 0.3–1.0 um | 8 species × 15 wavelengths; `14_bulk_table_config.py` |
| 15 | All-species scalar table over 10–12 um | 8 species × 21 wavelengths; `15_bulk_table_10p0_12p0um_config.py` |
| 16 | Eight separate measured-format PSD tables | `16_measured_psd_config.py` and the eight **synthetic** CSVs in `input_psd/measured_example/` |
| 17 | RTTOV13-style aerosol/ZJU cloud tables | 8 species × 5 wavelengths; actual P11 and default populations |
| 18 | Fixed-population RTTOV14 version-4 files | Matching config; `--reuse-bulk` optionally reuses a matching table/report from 17 |
| 19 | CRTM IR subset | Explicit material densities; optional matching `--reuse-bulk` |
| 20 | ARTS 2.x SSD XML | All six phase elements; optional matching `--reuse-bulk` |
| 21 | RTTOV14 effective-radius/RH/temperature master grids | Run 17 first for its source report; optional catalog; full configuration can take time |
| 22 | The same grids with custom BC/dust/ice shapes | Inherits configuration 21; runs its shared driver |
| 23 | Rename default lookup populations to two-letter codes | Run 21 first; preserves optical arrays and axis values |
| 24 | Custom NetCDF/HDF5 layout | Run 17 first, or set `bulk_source` in `24_custom_output_config.py` |
| 25 | Single-particle figures | Run 08 first, or supply a native NetCDF path |
| 26 | Bulk figures | Run 12 first, or supply a canonical bulk path |
| 27 | JSON CLI retrieval | `request.json`; source files and reports under the example's `downloads/json_seasalt/` |

Every numbered configuration remains beside its driver. Shared configurations are
not imported from another numbered example. Generated output stays under
`downloads/` beside this collection; supported `--output-dir`/config overrides can
select other destinations. Reference table workspaces can use the normal user cache.
No downloaded optical files or prior calculation products are shipped here.

## Start with previews

```console
python examples/research_workflows/03_download_seasalt_1p5um.py --list-only
python examples/research_workflows/08_download_ice_250k_1p6um_shape_interpolation.py --list-only
python examples/research_workflows/14_all_species_bulk_0p3_1p0um.py --help
```

A selection preview may contact the catalog and write a report, but does not
download optical data. Ordinary runs may download significant amounts of data.
Table configurations use a saved catalog when it exists and otherwise use the
interface's live discovery. Do not copy a catalog containing obsolete paths into
the new collection merely to avoid a fresh source-selection check.

## Example execution order

The retrieval examples are independent. Examples 11–13 retrieve their own required
sources. Examples 14–20 can build their configured tables; 15 can also prepare local
sources useful for the IR examples. For the dependent inspection/export chain:

```console
python examples/research_workflows/17_default_bulk_rttov13.py
python examples/research_workflows/21_default_bulk_rttov14_lookup.py
python examples/research_workflows/22_custom_shapes_rttov14.py
python examples/research_workflows/23_default_scheme_rttov14_two_letter.py
python examples/research_workflows/24_export_custom_output.py
```

Use `--offline` only after the corresponding source dependencies are available.
Use `--slice-only` on 21/22 to select existing master files without rebuilding.
Example 23's `--recompute` rebuilds the default grids before renaming. It is not
a custom-shape export of example 22. Example 24 protects existing exports unless
`--overwrite` is deliberately supplied.

## Scientific conventions and model limitations

PSDs contain radius-bin concentrations in `cm-3`, not differential densities.
The supplied measured-format files are synthetic fixtures; replace them with
properly converted measurements for research. Preserve the stated size definition,
weights, RI scheme, concentration and coverage policy. Reference presets describe
explicit assumptions and are not measured climatologies.

Some size-grid coarsening diagnostics in examples 14–20 exceed the default 5%
relative-difference threshold. The check thins optical nodes and remaps PSD bins;
it measures sensitivity rather than bounding the full result's error. Increasing
analytical PSD bins from 400 to 1,600 did not remove the warnings in controlled
checks. Sparse native optical sampling over small aerosol populations and small
asymmetry values contribute. Thresholds and scientific inputs remain unchanged.
Inspect per-population diagnostics before using a table scientifically; see
[diagnostic interpretation](../../docs/SCIENTIFIC_REFERENCE.md#interpreting-the-5-size-grid-diagnostic).

ARTS/CRTM/RTTOV exports have different normalization/axis contracts. RTTOV13's
descriptive aerosol and ZJU cloud names require reader adaptation. The CRTM example
is an IR subset. RTTOV14 master cubes require appropriate slicing or a reader
adapter for stock runtime axes. No compiled radiative-transfer solver acceptance
is implied by file validation. See the maintained
[scientific reference](../../docs/SCIENTIFIC_REFERENCE.md#7-downstream-model-formats).

The [user manual](../../docs/USER_MANUAL.md) and
[function reference](../../docs/FUNCTION_REFERENCE.md) cover the interface itself.
Keep session tokens outside scripts, configurations and result bundles.
