# Examples

<img src="../docs/assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

The [research workflow collection](research_workflows/README.md) contains 27
complete retrieval, PSD, bulk-table, model-export and plotting examples with
adjacent configurations and synthetic PSD inputs, numbered consecutively 01–27.
Original local maintenance examples 05–07 were excluded before renumbering.
The examples listed below are a separate introductory/validation series.

Run these scripts from the project root.  The filenames follow the pattern
`example_<two-digit-order>_<purpose>.py`; each script has a small reusable
function plus a command-line entry point, so it can be read top-to-bottom,
called from a notebook, or rerun from WSL.  Generated files are written to an
explicit output path or directory; the checked-in source data under
`examples/data/` is never modified.

## 1. First contact: catalog and configuration

| Script | Purpose | External data required? |
|---|---|---|
| `example_01_catalog_search.py` | Search catalog metadata without downloading file contents. | Website/catalog access |
| `example_02_target_wavelength_retrieval.py` | Select and download source files for target wavelengths, including interpolation products. | Website/catalog access and writable cache |
| `example_03_bulk_scheme_validation.py` | Load and validate a Python-dictionary bulk scheme. | No |

## 2. Reader workflows: PSDs, interpolation, and outputs

| Script | Purpose | External data required? |
|---|---|---|
| `example_04_observed_psd_csv.py` | Load measured bin counts unchanged and save a validated configuration and plot/report. | No; uses `examples/data/` |
| `example_05_interpolation_modes.py` | Demonstrate exact retrieval, interpolation, nearest planning, and no-extrapolation errors. | No; synthetic optics |
| `example_06_weighted_ice_shapes.py` | Use common size coverage, per-shape integration and a weighted average. | Yes; pass compatible files/directories with `--source` |
| `example_07_multidimensional_bulk_scheme.py` | Build retained grids for multiple independent particle types. | Yes; pass ice and sulfate L1 sources |
| `example_08_export_model_table.py` | Convert a canonical NetCDF/HDF5 product into a configurable text table. | Yes; pass a canonical product |
| `example_17_native_model_formats.py` | Integrate synthetic optics and write native ARTS XML, CRTM NetCDF/binary, RTTOV13 HDF5 and JSON templates. | No; optional RTTOV cloud reference |

For model versions, variable layouts, units and official-reference verification,
see [Downstream model formats](../docs/SCIENTIFIC_REFERENCE.md#7-downstream-model-formats).

The [extension walkthrough](../docs/EXTENDING.md) explains how a user-defined
capability joins these existing workflows.
[example_18_custom_psd_extension.py](example_18_custom_psd_extension.py) is a complete
first extension: register a named PSD factory, integrate synthetic optical samples,
and save checked results. It needs registration but no optical downloads.

## 3. Validation walkthroughs

The Phase 4–11 scripts are larger, self-contained demonstrations of the
validation work.  They create synthetic fixtures unless noted otherwise and
write a JSON report plus any diagnostic figures to `--output-dir`.

| Script | Focus |
|---|---|
| `example_09_phase4_psd_validation.py` | PSD input, CSV round-trip, conservative remapping, and bulk integration. |
| `example_10_phase5_interpolation_validation.py` | Multidimensional optics interpolation and phase-matrix alignment. |
| `example_11_phase6_particle_adapter_validation.py` | Water, sulfate, and sea-salt particle adapters. |
| `example_12_phase7_bulk_pipeline_validation.py` | Component-separated bulk calculations, ensembles, QA, and convergence. |
| `example_13_phase8_output_validation.py` | NetCDF4/HDF5 writing, reading, validation, and scientific equivalence. |
| `example_14_phase9_typed_and_cli_validation.py` | Typed-Python and declarative JSON/CLI equivalence. |
| `example_15_phase10_usability_validation.py` | Recipes, units, registry, observed PSD, machine reference, and graphics. |
| `example_16_phase11_release_readiness_validation.py` | Local tests, build, metadata, artifact contents, clean wheel installation, and report; never publishes. |

## Common commands

```bash
# Run a synthetic example and inspect its JSON report.
python examples/example_04_observed_psd_csv.py --output-dir observed_psd_output

# Run one validation walkthrough.
python examples/example_13_phase8_output_validation.py --output-dir phase8_output

# Limit a retrieval to one target/file for a quick connectivity smoke test.
python examples/example_02_target_wavelength_retrieval.py \
    --target-wavelengths-um 0.6 --max-files 1 --data-dir retrieve_smoke

# Run the example-focused tests.
python -m unittest -v tests.test_phase4_example tests.test_phase5_example \
    tests.test_phase6_example tests.test_phase7_example tests.test_phase8_example \
    tests.test_phase9_example tests.test_phase10_examples
```

The scripts use Matplotlib's non-interactive `Agg` backend when they create
figures, so they can run in a headless WSL shell.  Install the NetCDF/HDF5
extras before running examples that read or write those formats.  Phase 11
also requires the local `ruff`, `build`, and `twine` command-line tools because
it checks packaging readiness without publishing.  Complete declarative
recipes are in `configs/recipes/`; the demonstrated PSD values are examples
rather than atmospheric recommendations.

Examples 06 and 07 accept multiple source files after each source option, or a
directory containing all required source coordinates. One fixed-shape file
alone cannot support an entire shape/temperature ensemble.

To audit each example/configuration against the installed interface:

```bash
python examples/audit_example_interfaces.py --output-dir example_audit --run
```

This checks syntax, imports, call signatures, configuration loading, command
help and the explicitly listed synthetic workflows. Add `--cached` in this
development workspace to check saved-source plans and cached format exports
with network connections blocked. The per-file report distinguishes these
checks from live retrieval/full lookup calculations, which it does not run.
