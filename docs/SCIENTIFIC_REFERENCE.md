# Scientific and data-format reference

<img src="assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

This reference defines the scientific conventions used by the built-in workflows.
For execution steps use the [user manual](USER_MANUAL.md); for exact signatures
use the [function reference](FUNCTION_REFERENCE.md). Registered extensions can
define additional capabilities, so inspect the installed machine reference before
assuming that this built-in overview is exhaustive.

## Contents

1. [Units and physical coordinates](#1-units-and-physical-coordinates)
2. [Size distributions](#2-size-distributions)
3. [Particle profiles and optical constants](#3-particle-profiles-and-optical-constants)
4. [Interpolation, ensembles and boundaries](#4-interpolation-ensembles-and-boundaries)
5. [Reference presets](#5-reference-presets)
6. [Canonical data and diagnostics](#6-canonical-data-and-diagnostics)
7. [Downstream model formats](#7-downstream-model-formats)

## 1. Units and physical coordinates

| Quantity | Input/storage convention | Interpretation |
|---|---|---|
| Wavelength | `nm`, `um`, or wavenumber `cm-1`; normalized to `um` | Positive vacuum wavelength; `um = nm/1000 = 10000/(cm-1)` |
| Particle size | Radius in `nm` or `um`; normalized to `um` | Use the explicitly selected size definition |
| PSD `dndr` | `cm-3` per represented bin | Bin concentration, not a differential density |
| Temperature | `K` | Required for the ice profile |
| Relative humidity | Fraction, normally bounded by the profile to `0–0.99` | `0.8` means 80%; downstream percent grids are explicit exceptions |
| Cross section | Physical `m2` in loaded optics | Native files may store dimensionless scaled cross sections |
| Bulk extinction/scattering/absorption | `m-1` | Population coefficients |
| SSA and asymmetry | `1` | Dimensionless intensive quantities |
| Phase elements | `1` in canonical bulk optics | Check normalization and native ratio representation |
| Scattering angle | Degrees | Preserve coordinate order and coverage |

`volume_equivalent_sphere_radius` is the radius of a sphere with the particle's
volume. `maximum_dimension_radius` is `Dmax/2`, not full maximum dimension.
Their relationship depends on geometry; changing a label does not convert the
coordinate. Use paired source geometry or a verified converter with a recorded
geometry source. For BC, check whether the source's size coordinate refers to the
core rather than the full coated particle.

### Native size parameters and Cext

Native `xsize_veq`/`xsize_maxd` can be dimensionless size parameters. For the
volume-equivalent coordinate,

```text
x = 2*pi*r/lambda
r_um = x*lambda_um/(2*pi)
```

A file storing `cext = Cext*k²`, with `k = 2*pi/lambda`, does not store physical
`Cext` directly:

```text
Cext_m2 = cext*(lambda_m/(2*pi))**2
```

The optics loader performs the supported physical interpretation using metadata
and loading controls. Automatic source retrieval preserves the native schema,
including this dimensionless representation. Do not apply the conversion twice
or treat the native quantity as an extinction efficiency. Explicit native-grid
RI without a physical wavelength cannot establish physical cross-section scaling.

## 2. Size distributions

### Discrete-bin contract

`SizeDistribution` contains one-dimensional positive radius coordinates and
finite nonnegative corresponding bin concentrations. Its public integration mode
is `discrete_bin`; its `dndr_unit` is `cm-3`.

```text
N_cm3 = sum(dndr[i])
N_m3 = 1e6*N_cm3
```

The historical name `dndr` does not imply `cm-3 um-1`. If an instrument supplies
a bin-average `dN/dr`, integrate it over the actual radius-bin widths. For
`dN/dlog10(D)`, integrate over log10 diameter-bin widths instead. Verify edge
definitions, logarithm base, units and whether values are bin averages or point
samples. Centers alone do not uniquely determine measurement-bin edges.

Diameter-to-radius conversion leaves already-integrated counts per bin unchanged.
A differential density additionally requires the appropriate variable
transformation. Convert counts in `m-3` to `cm-3` by dividing by `1e6`.
Changing an arbitrary distribution to unit concentration is a scientific choice,
not an input-cleaning step.

### Analytical distributions

`lognormal_psd` uses geometric mean **radius** `rg_um`, geometric standard deviation
`sigma_g`, concentration, optional finite bounds and a bin count. A geometric mean
diameter of 1.4 um corresponds to `rg_um=0.7`.

`gamma_psd` uses effective radius and effective variance, with
`0 < effective_variance < 0.5`. On the volume-equivalent-radius distribution,

```text
M_j = sum(N_i*r_i**j)
r_eff = M_3/M_2
v_eff = M_4*M_2/M_3**2 - 1
```

This is not a nonspherical projected-area effective radius. Both factories use
CDF-integrated bin counts rather than sampling a density at centers. The finite
representation records retained probability and realized moments.

| Normalization policy | Meaning |
|---|---|
| `preserve` | Retain the original parent population inside the finite bounds; represented concentration can be smaller than the requested parent concentration |
| `renormalize` | Scale the finite representation to the supplied concentration |

Measured `SizeDistribution` inputs preserve their supplied counts. Explicit
`normalized(...)` creates a rescaled distribution. Record any normalization.

### Remapping and truncation

Integration remaps counts conservatively to compatible source grids and uses the
selected physical size definition. Coverage follows bin support, not merely the
smallest/largest center. All sources and ensemble members must share supported
physical coverage for the requested calculation.

`truncation_policy="error"` rejects uncovered concentration. Explicit `"truncate"`
retains the common supported population and reports loss; it does not silently
renormalize. Inspect the `RemapReport`, source-size coverage and realized PSD.
Sampling an apparently wide source in one wavelength does not establish coverage
at another wavelength or for every member.

## 3. Particle profiles and optical constants

Use the installed registry for parameter roles, aliases and bounds:

```console
zju-scatt describe --json
zju-scatt describe super_spheroid_ice --json
zju-scatt bulk-opt schema --json
```

The following overview describes the built-in profiles; source combinations and
finite optical data determine actual support. Nominal ranges are not a guarantee
of remote availability or a complete Cartesian grid.

| Canonical profile | Common alias | Main coordinates | Nominal wavelength range |
|---|---|---|---|
| `super_spheroid` | `dust` | Roundness, aspect ratio; RI-grid target or material-table wrapper | Positive scaling wavelength; packaged default table spans `0.3–20 um` |
| `encapsulated_fractal_aggregates_black_carbon` | `bc`, `black_carbon` | `df`, `vf`, selected database/RI scheme; four index components in explicit grid mode | Interface range `0.3–20 um` |
| `coated_super_spheroid_seasalt` | `sea_salt` | RH and `deliquescence`/`crystallization` branch | `0.2–40 um` |
| `super_spheroid_ice` | `ice` | Temperature, roundness, aspect ratio | `0.3–99 um` |
| `sphere_sulfate` | `sulfate` | RH | `0.2–40 um` |
| `sphere_nitrate` | `nitrate` | RH | `0.2–40 um` |
| `sphere_organic_carbon` | `organic_carbon` | RH | `0.2–40 um` |
| `sphere_water_cloud` | `water_cloud` | Wavelength | `0.3–100 um` |

Dust roundness is nominally `1.2–3` and aspect ratio `0.5–2`; ice roundness is
`2–3`, aspect ratio `1–2.5`, and native temperature coverage is nominally
`160–270 K`. BC `df` is `1.8–2.4` and `vf` is `0–1`, subject to actual native
nodes. `vf` means `Vbc/(Vbc+Vhygro)`; it is not an externally prescribed RH.

Parameter aliases include `n`/`ssph_n` for roundness,
`asp`/`ssph_asp` for aspect ratio, and `rh` for relative humidity. Prefer canonical
names in saved schemes. A supported alias is not a separate scientific coordinate.

### RI-grid versus wavelength-native data

Dust/generic super-spheroid files are indexed by refractive index. Physical
wavelength supplies size/cross-section scaling and can resolve target indices
through a material table. Complete explicit indices bypass that table; they do
not remove the need for wavelength when calculating physical optics.

For a dust adapter, explicit `mr`/`mi` are supported parameter aliases. For BC
grid calculations, supply all four `bc_mr`, `bc_mi`, `hygro_mr`, `hygro_mi`
together. JSON bulk schemes express this through `refractive_index` with
`mode="fixed"`; typed configs use the corresponding RI strategy object.
Partially specified material indices are not a justified complete optical model.

Wavelength-native sea salt, ice and hydrated spheres derive RI through their
database/environment coordinates and reject unsupported fixed user RI. Ice needs
temperature. Missing indices in supported wrapper workflows can select a packaged
default; record the resolved values and table identity.

Dust's packaged default is `Dust_refractive_index_statistics.csv`. BC has
separate core and coating tables. Defaults differ across retrieval, adapter and
reference-preset workflows; inspect the resolved `ri_scheme` rather than assuming
one global default. `default_refractive_index_paths` identifies canonical table
locations for a supported scheme.

### BC's independent database types

BC also has a distinct wavelength-based dataset. Select `database_type` explicitly
when the distinction matters. `ri_scheme` identifies prescribed optical-constant
schemes such as `v1.2.1` and `v1.2.2`; these are different scientific assumptions,
not interchangeable revisions of the same calculation.

Broad family RI bounds do not imply every native grid spans them. The grid and
wavelength datasets can have different morphology sampling, size support and
available index combinations. A wavelength inside `0.3–20 um` can resolve to an
RI outside the selected grid. The wavelength dataset's existence does not extend
that grid or authorize interpolation between the two families.

Read each selected file's size coordinates and revision. Dimensionless size
support becomes wavelength-dependent physical size support. Use the intersection
of converted finite ranges over all neighbors, rather than the union. Source
filenames and processing reports distinguish database types; parent folder names
alone may not.

## 4. Interpolation, ensembles and boundaries

The adapters select source nodes appropriate to the particle coordinates. Exact
nodes can be reused directly. In-domain interpolation can use multilinear or
sparse-grid support, with neighbor coordinates/weights retained as provenance.
Partial and unsupported series must be inspected rather than treated as complete.
Required source stencils must not be silently reduced by download/file limits.

Native source revisions remain distinct. Do not mix revisions to fill missing
corners of an interpolation stencil. Nearest selection answers a different
question from interpolation and must be deliberate. Source-level shape ranges
filter geometry; they do not necessarily request interpolated geometry.

Extrapolation is not silently performed. Behavior at unsupported boundaries
depends on the adapter and operation: some requests fail, while supported ice/BC
boundary policies can return warning/provenance-bearing NaN products. A numeric
array, a NaN product and a validation exception require different interpretations.
Inspect the selected sources, finite mask and issues. Do not replace NaNs with
zeros or describe all produced files as scientifically supported results.

### Weighted populations

Independent `WeightedValues` form a Cartesian product with multiplied weights.
`WeightedShapeEnsemble` preserves correlated member tuples. Each member is
interpolated/integrated before combination. Input shape parameters are not averaged
first. Finite nonnegative weights with a positive sum are normalized and recorded.

For member coefficients `beta` and number-fraction weights `w`, the combined
extensive coefficients are sums of `w*beta`. SSA is re-derived from combined
scattering/extinction; asymmetry and phases are scattering weighted. Do not
arithmetic-average SSA or asymmetry. In member reports, a member can describe a
hypothetical pure population at the recorded concentration; its allocated share
is determined by the ensemble weight.

Separately named scheme components retain their independent concentrations and
outputs. Retained grid dimensions preserve states instead of averaging them.
An explicit external combination must state its physical interpretation.

### Phase data and QA

The random-orientation convention uses six independent elements `p11`, `p12`,
`p22`, `p33`, `p43`, `p44`. Native files can represent non-P11 fields as ratios
to P11; loaders/converters must honor that representation. Preserve sufficient
angular resolution for the downstream quantity, especially sharply peaked phases.

Inspect physical QA, convergence, phase normalization, PSD remapping and member
provenance separately. A passing file schema or disabled convergence check is not
evidence of numerical convergence. Preserve/error/renormalization options for
phase data are explicit scientific policies, not interchangeable formatting flags.

### Interpreting the 5% size-grid diagnostic

The current convergence check keeps alternate optical radius nodes, retains both
endpoints, conservatively remaps the same input PSD onto the reduced grid, and
compares extinction, SSA and asymmetry with the full-grid calculation. Its default
threshold is a **relative difference of 5% for each quantity**. This is a
coarsening sensitivity test, not an independent error bound on the full result.
It includes both optical sampling and the change in PSD bin representatives.

In the research examples originally numbered 17–23 (release examples 14–20),
warnings persist for some small aerosol populations even though physical QA
passes. At IR wavelengths, only a small subset of the optical size axis can lie
inside the populated PSD range. Removing half those nodes can noticeably change
the weighted coefficients. Relative differences in asymmetry can also be large
when asymmetry itself is close to zero; inspect the absolute values as well.

Controlled checks on the supplied sources increased analytical PSD sampling from
400 to 1,600 bins at unchanged bounds, concentration and parent parameters.
The tested single-shape scalar results changed by less than 0.04%, while warnings
remained. A separate test reconstructed thinned optical data onto the full grid
before integration, holding the PSD remapping fixed; some differences still
exceeded 5%. Increasing PSD bins therefore does not resolve all these warnings.
Neither experiment establishes the accuracy of the native optical data.

Keep the threshold and inspect `report.json` member diagnostics. Establish accuracy
with independently finer native optical data or an appropriate independent
calculation where available. Interpolating extra optical nodes adds no independent
source information. Change a population or coverage policy only when scientifically
justified, and record that change; a different PSD is a different experiment.

## 5. Reference presets

`literature_v1` supplies editable reference assumptions used by the table workflow.
The maintained implementation records its literature provenance and resolved
parameters in the table report. `reference_v1` retains earlier illustrative choices.
Neither is a universal measured population; use sample-specific inputs when known.

| Species | Reference geometry/environment | Parent PSD |
|---|---|---|
| Dust | Roundness 2.6; equal number fractions across registered aspect ratios `0.5–2.0` | Lognormal `rg=0.5 um`, `sigma_g=2.0` |
| BC | `df=2.1`; target `vf=0.3`, resolved against common native support; native wavelength RI scheme | Lognormal `rg=0.1 um`, `sigma_g=1.5` |
| Sea salt | Crystallization branch, RH `0.60` | Lognormal `rg=0.1 um`, `sigma_g=2.0` |
| Ice | `220 K`; paired shapes `(2.5,1.75)`, `(2.5,2.0)`, `(2.75,2.0)` with equal fractions | Gamma `r_eff=30 um`, `v_eff=0.1` |
| Water cloud | Native spherical profile | Gamma `r_eff=10 um`, `v_eff=1/3` |
| Sulfate | RH `0.60` | Lognormal `rg=0.07 um`, `sigma_g=1.6` |
| Nitrate | RH `0.60` | Lognormal `rg=0.07 um`, `sigma_g=1.6` |
| Organic carbon | RH `0.60` | Lognormal `rg=0.02 um`, `sigma_g=1.8` |

Reference concentration defaults to `1 cm-3` per independent species. The table
workflow restricts analytical PSDs to common physical support over the requested
spectrum and records retained probability and realized moments. Inspect the actual
report for conditional reference normalization, resolved native `vf`, chosen RI
scheme and overrides. A reference preset's bounded/normalized PSD is not identical
to an unconstrained parent distribution.

Measured PSD overrides must retain their stated interpretation. Custom clipping
and renormalization require explicit policies; do not infer permission from the
fact that a reference preset itself uses finite bounds.

## 6. Canonical data and diagnostics

Canonical NetCDF4 and HDF5 implement `zju_scatt_bulk_optical_scheme`, schema `1.0`.
The writer can export complete datasets, population results, retained grids,
table results, bare bulk optics and supported homogeneous sequences. Equivalent
formats retain scientific content, not identical binary representations.

For ordinary datasets, each named component has its own group and wavelength
coordinate. The grouped writer does not duplicate wavelength at the root.
Attributes record interface/schema information and supplied scheme/source/dependency
metadata. Supply complete results and provenance rather than attempting to rebuild
them from filenames.

| Component variable | Dimensions for an ordinary spectrum | Unit |
|---|---|---|
| `wavelength` | wavelength | `um` |
| `beta_ext`, `beta_sca`, `beta_abs` | wavelength | `m^-1` |
| `ssa`, `g` | wavelength | `1` |
| `number_concentration` | wavelength | `cm-3` |
| `psd_size`, `psd_dndr`, when retained | psd_size | `um`, `cm-3` respectively |
| `sca_angle`, when phases are present | sca_angle | degree |
| Six phase elements | wavelength, sca_angle | `1` |
| `ensemble_member` | ensemble_member | Zero-based index |
| `shape_weight` | wavelength, ensemble_member | `1` |

Ensemble coordinates include `ssph_n`, `ssph_asp`, `mr`, `mi` and supported
environment/BC fields. `temperature` uses K; other dimensionless geometry/RH
fields use `1`. Member index is not a physical coordinate or population fraction.
Retained grid products use their declared bulk-state axes instead of the ordinary
one-dimensional spectrum layout, with a trailing angle dimension for phases.

QA and convergence flags are retained in calculation/JSON summaries rather than
added as canonical optical data variables. `PopulationResult.save` retains richer
diagnostics; the CLI summary alone is not a complete member report. `read` returns
a canonical mapping, not reconstructed computation objects. File validation checks
schema, units, shapes and applicable physical consistency; it cannot recover an
unrecorded scientific assumption or establish suitability for a research question.

Canonical writes validate temporary products before atomic replacement. Custom
multi-file export is not an all-or-nothing transaction. Keep output directories
separate by experiment and preserve diagnostic bundles alongside data files.

## 7. Downstream model formats

Canonical ZJU-SCATT output is not a universal ARTS/CRTM/RTTOV input. Distinguish
custom text/layout output, high-level model exporters and lower-level templates.
The implemented target/version and required normalization determine compatibility.

| Workflow | Implemented target | Main limitation |
|---|---|---|
| `write_arts_bulk_tables` | ARTS 2.x, SSD XML version 3, totally random orientation | Fixed-PSD effective element; requires all six phases and consistent normalization |
| `write_crtm_ir_bulk_tables` | CRTM IR optical-table subset | Not a complete arbitrary CloudCoeff dataset or proof of compiled-reader acceptance |
| `write_rttov13_bulk_tables` | RTTOV13-style SCAER and ZJU-named fixed-PSD clouds | Descriptive aerosol/ZJU cloud names require reader changes |
| `write_rttov14_bulk_tables` | RTTOV14 version-4 fixed-population NetCDF aertable/hydrotable | Thermal-IR subset; no compiled RTTOV14 acceptance claim |
| `build_rttov14_lookup_tables` | Retained radius/RH/ice-temperature master tables | Stock runtime axes require an appropriate slice or adapter |
| `io.native` templates | Explicit ARTS/CRTM release-3/RTTOV13/custom arrays | Caller must supply the required arrays and validate against the intended reader |

These declarations do not imply ARTS 3/oriented-particle support, CRTM AerosolCoeff,
every CRTM release, or RTTOV microwave/radar support. Preserve the target reader's
version and channel ordering. Export does not integrate a sensor spectral response
or extrapolate missing spectral/size/environment data.

### ARTS

For totally random orientation the phase order is
`Z11, Z12, Z22, Z33, Z34, Z44`. Convert canonical phases using
`beta_sca/(4*pi*N_m3)` and the sign relation `Z34 = -P43*beta_sca/(4*pi*N_m3)`.
Extinction/absorption become `beta/N_m3` in `m2` per effective particle.
Canonical P11 must have the required 4π solid-angle normalization.

SSD axes include increasing frequency in Hz, temperature in K and angle in
degrees. The phase tensor layout is `(frequency, temperature, angle, 1, 1, 1, 6)`;
extinction/absorption use `(frequency, temperature, 1, 1, 1)`. Frequency sorting
must move the data with the coordinate. Missing phases or incomplete Cartesian
grids are not repaired by inventing values.

### CRTM

Mass extinction uses `beta_ext/mass_concentration_kg_m3`, in `m2 kg-1`.
Material densities and, where needed, growth factors must be specified for the
high-level IR workflow. Preserving PSD bin counts is separate from deriving a
mass concentration.

Full release-3 templates distinguish MW liquid, MW solid and IR arrays. On-disk
NetCDF dimension order reverses Fortran declarations. Packed stream-set phase
coefficients are not a single sequence of angular samples or one simple degree
axis. Native helpers implement the supported packing and binary layout; an IR-only
calculation does not supply uncomputed MW blocks. Preserve that scope in reports.

### RTTOV13

High-level cloud groups identify the ZJU populations; descriptive aerosol names
also differ from stock short-name assumptions. Modify the intended reader's name
handling when using these outputs. Lower-level reference-derived templates preserve
their reference contract separately.

Aerosol absorption/scattering are normalized per particle concentration in `cm-3`.
Cloud mass conventions differ; do not apply aerosol number normalization to cloud
mass coefficients. Relative humidity is percent in this model format, diameters
are um, and channel indices/ordering follow the target file. HDF5 Fortran bounds
must be interpreted in reverse dimension order relative to Python shapes.
The Chou backscattering parameter requires phase information; it cannot be inferred
from asymmetry factor alone.

### RTTOV14

Fixed-population outputs use separate version-4 aertable/hydrotable files and
fields including `ext`, `ssa`, `asym`, `bpr`, `nmom`, `lcoef`. Aerosol extinction
is `km-1` per particle/`cm3`; hydrometeor extinction is `km-1` per `g/m3`.
When passing a canonical bulk file to this high-level exporter, retain the required
sibling `report.json` with PSD/mass information. File storage alone may not retain
all inputs needed by an application exporter.

The lookup-builder argument `relative_humidity_percent` explicitly uses percent,
unlike ordinary scientific `relative_humidity`. Retained master cubes include
radius and environmental axes. `write_rttov14_lookup_slice` selects exact nodes for
the supported stock RH-only/Deff-only runtime paths. Master cubes require a reader
adapter if joint-axis interpolation is desired; writing the cube does not implement
that adapter. Use the dedicated fixed-population or lookup validator as appropriate.

For any target, retain the export manifest, required normalizations, phase policy,
coordinate selections and validation report. Validate against the exact downstream
reader before claiming operational compatibility.
