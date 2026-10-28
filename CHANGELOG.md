# Changelog

<img src="docs/assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

## 1.0.0 - 2026-10-28

- Added `zju_scatt` and `zju_scatt_interface` CLI aliases alongside the existing
  hyphenated commands, with the Python import name unchanged.
- Corrected the public `access.search_data` and `access.estimate_data` exports to
  use their existing retrieval implementations. The function reference now
  documents both helpers, and documentation checks reject unresolved exports.
- Reworked the extension guide around the workflow model, registration lifecycle
  and extension responsibilities, with a complete named-PSD tutorial and checked
  synthetic calculation in `examples/example_18_custom_psd_extension.py`.
- Made release installation instructions PyPI-first, shortened the dependency
  opt-out note, and removed conda instructions. Added a citation placeholder for
  the interface paper by Senyi Kong and Lei Bi.
- Moved package contents directly under `src/`, retaining the public
  `zju_scatt_interface` import and CLI names through setuptools package mapping.
  Updated source inspection, editable-install checks and release staging.
- Standard installation now installs NumPy, h5py, netCDF4 and Matplotlib
  automatically. Documented an explicit retrieval-only `--no-deps` installation
  and its metadata limitations. Existing scientific extras remain compatible.
- Designated the current interface as version `1.0.0`. This source version
  designation does not imply publication to a package index.
- Consolidated release documentation into a user manual, function reference,
  scientific reference, extension guide and AI research skill; expanded the
  project README with installation, workflow and maintenance guidance.
- Added 27 verified research workflow examples, numbered consecutively 01–27,
  with portable configurations and synthetic measured-format PSD inputs.
- Investigated size-grid convergence warnings. They remain visible at the
  unchanged 5% threshold; this release designation does not establish independent
  numerical convergence for every supplied population. See the scientific
  reference for diagnostic interpretation and limitations.

- Fixed RTTOV14 lookup slicing when a master contains only one wavelength;
  NetCDF scalar attributes now retain the spectral axis. Added cached-workflow
  `--no-track` switches to the local ensemble examples (release examples 11–13)
  and verified all local scripts.

- Added explicit extension contracts and duplicate-safe registration for particle
  definitions, named PSD factories, product/workflow operations, application
  exporters, native models/serializers, plot kinds and CLI commands. Public
  dispatchers now use registered handlers. See `docs/EXTENDING.md`.
- Moved shared application preparation out of RTTOV and native model policies
  into the ARTS, CRTM and RTTOV application packages. Retained existing scientific
  integration, schemas, units and built-in entry points.
- Added isolated extension acceptance tests, including numerical comparison and
  verification that registering new implementations leaves existing source files unchanged.

- Grouped ARTS and CRTM exporters into application subpackages alongside RTTOV:
  `io.applications.arts.bulk` and `io.applications.crtm.ir`.
- Breaking architecture overhaul: implementations now live in `access/`,
  `config/`, `sources/adapters/`, `optics/`, `psd/`, `bulk/`, `io/applications/`,
  `plotting/`, and `cli/`. Removed the monolithic `_engine`, flat module aliases,
  `compat` exports and the root legacy-import fallback. Prior code is preserved
  outside the active package under `versions/interface_before_domain_overhaul_20261026`.
- Renamed actual scientific model/workflow definitions and removed duplicate
  format-specific canonical writers. Use the small root API and `io.write`.
  The redundant `compute-bulk` command alias is removed; use `bulk`.
- Migrated maintained tests, examples, configurations and scripts to owning
  domain modules. Scientific settings, output schemas and diagnostic bundles
  are retained. See `docs/EXTENDING.md` and `docs/FUNCTION_REFERENCE.md`.
- Added `zju-scatt plot FILE` with automatic single-particle/canonical-bulk
  detection, explicit `--kind` overrides, and the existing plotting selection
  and output options.
- Normalized manifest paths loaded from retrieval JSON configurations and added
  Windows extended-length filesystem handling for deeply nested downloads and
  generated NetCDF products.

## 0.9.0 - 2026-10-13 (prepared, not published)

- Set the initial public release candidate to `0.9.0`; plan further testing and
  `0.9.x` fixes before considering `1.0.0`. Earlier `1.0.0a1` entries below
  describe internal development checkpoints, not this public release.

- Included the September 2026 revised dust and black-carbon statistics and six
  material reference CSVs in the release candidate.
- Recognized `Wavelength (in micrometers)` reference-table headers and tested all
  twelve explicit ice temperature-column pairs.
- Added a regression check for the revised black-carbon means, clean staging and
  artifact verification for releases, and a PyPI publication guide.
- Read build-time version metadata directly from `_version.py` and included tests,
  Python scheme configurations, and the changelog in source distributions.

- Revised single-particle interpolation to combine logarithmic dimensional cross
  sections and projected area, derive SSA/efficiencies afterward, interpolate
  source-normalized phase ratios, and expose solid-angle-weighted phase L2 metrics.
- Added template-driven optical table export from in-memory results or canonical
  NetCDF4/HDF5 products, with JSON/Python format specifications, unit transforms,
  fixed-width rows, per-particle files, and phase-matrix long tables.
- Added retained multidimensional bulk-optics grids through `BulkDimension`,
  `SingleBulkScheme`, and `MultiBulkScheme`, including particle-specific NetCDF4
  and HDF5 dimensions, coordinate variables, phase matrices, and validation.
- Separated single-population calculation, custom aggregation, and output;
  removed implicit `mixing_fraction` and `include_mixture` scheme behavior.
- Added Phase 11 eight-profile exact/interpolated fixture coverage, trusted
  numerical references, output-corruption tests, opt-in live tests, expanded CI,
  artifact checks, and clean-install validation.
- Corrected interpolation aliases so source symbols `n` and `alpha` map to
  `roundness` and `aspect_ratio`.
- Separated package identity, exceptions, endpoints, and optical models from the
  private compatibility engine.
- Completed Phase 10 user workflows with full BC, dust, sea-salt, and
  multi-temperature ice recipes.
- Added observed-PSD CSV and interpolation/nearest/no-extrapolation examples.
- Added `bulk-opt schema` and Python machine-reference APIs for deterministic
  GPT-assisted scheme creation.
- Added complete parameter, recipe, GPT-safety, and troubleshooting documentation,
  plus Phase 10 tests and graphical validation.

## 1.0.0a1 - Phase 2 registry work

- Added canonical scientific profiles for all eight local L1 particle families.
- Added `zju-scatt describe [PARTICLE_TYPE]` and JSON metadata output.
- Added optional L1 NetCDF source-schema and major-revision validation.
- Added automatic extended-length Windows paths for long scientific filenames.
- Documented empirical profile coverage, RH storage conventions, and size meanings.
- Converted L1 `cext = k^2 Cext` to physical cross sections in `m2`.
- Converted `xsize_veq` and `xsize_maxd` to physical radii in `um`.
- Converted user number concentrations from `cm-3` to `m-3` internally so bulk
  coefficients are returned in `m-1`.
- Prevented silent flattening of multidimensional RH, volume-fraction, and shape
  dimensions.

## 1.0.0a1 - Phase 1 checkpoint (2026-07-23)

- Preserved the tested earlier command behavior behind the modular package.
- Added explicit direct and browser-assisted registration methods.
- Added actionable first-run and expired-session recovery guidance.
- Added the read-only `zju-scatt doctor` command with human and JSON reports.
- Added Windows, Linux, and macOS installation documentation.
- Added clean-install CI coverage for supported platforms and Python versions.
- Recorded the Python-first bulk-scheme design and minimal single-scattering-variable
  policy for subsequent phases.
