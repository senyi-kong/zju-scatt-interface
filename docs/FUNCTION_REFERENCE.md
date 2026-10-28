# Function and object reference

<img src="assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

This reference covers every resolvable function explicitly exported by the root
package and its non-CLI public namespace `__all__` lists, plus the documented
native-output, default-assumption and analytical-moment helpers. Aliases share
one entry. Internal underscore helpers and CLI implementation callbacks are not
the research API; use the [manual](USER_MANUAL.md) for commands and examples.

Coverage: **93 distinct functions**, **75 exported types**
(including exceptions/enums), and the non-inherited public methods listed below.
Inherited component parsing/serialization methods are documented once on
`ParticleComponent`; leaf component constructors remain listed individually.

Signatures/defaults are inspected from the current source. A `*` starts
keyword-only arguments; omitted return annotations are supplemented by the
reviewed Returns text. Callback defaults are named without process addresses.
A signature describes accepted arguments, not proof that a scientific target
is available. Registration, optional dependencies and physical conventions
still apply; see the [scientific reference](SCIENTIFIC_REFERENCE.md).

## Contents

- [zju_scatt_interface](#functions-1)
- [zju_scatt_interface.access](#functions-2)
- [zju_scatt_interface.bulk](#functions-3)
- [zju_scatt_interface.config](#functions-4)
- [zju_scatt_interface.extensions](#functions-5)
- [zju_scatt_interface.io](#functions-6)
- [zju_scatt_interface.io.applications](#functions-7)
- [zju_scatt_interface.optics](#functions-8)
- [zju_scatt_interface.optics.retrieval](#functions-9)
- [zju_scatt_interface.plotting](#functions-10)
- [zju_scatt_interface.psd](#functions-11)
- [zju_scatt_interface.sources](#functions-12)
- [zju_scatt_interface.sources.adapters](#functions-13)
- [zju_scatt_interface.io.native](#functions-14)
- [zju_scatt_interface.bulk.defaults](#functions-15)
- [zju_scatt_interface.psd.analytical](#functions-16)
- [Types and object methods](#types-and-object-methods)

<a id="functions-1"></a>
## zju_scatt_interface

### `load_scheme`

Load a portable bulk scheme.

```text
load_scheme(path: 'Union[str, Path]') -> 'Scheme'
```

**Inputs:** path: JSON or a trusted Python file defining bulk_scheme, BULK_SCHEME or config. Relative scientific paths are resolved beside that file.

**Returns:** Scheme; malformed/unsupported input raises. Python input executes code.

**Also exported as:** `zju_scatt_interface.config.load_scheme`.

### `describe_particle`

Describe one registered particle family (root alias: describe_particle).

```text
describe_particle(particle_type: 'str') -> 'ParticleProfile'
```

**Inputs:** particle_type: canonical name or registered alias.

**Returns:** ParticleProfile with parameters, roles, bounds, native coordinates and source requirements.

**Also exported as:** `zju_scatt_interface.config.get_particle_profile`.

### `plan`

Inspect a scheme's source dependencies without optical downloads.

```text
plan(scheme, **options)
```

**Inputs:** scheme: Scheme, compatible mapping or scheme path. Options follow prepare_scheme_dependencies, except download=True is rejected. workspace and offline control catalog/cache inspection.

**Returns:** DependencyPlan for built-in schemes. May inspect the network and write manifests; an incomplete plan records issues.

### `retrieve`

Run checked single/batch retrieval from a configuration.

```text
retrieve(config, *, download=None, output_dir=None, manifest=None, overwrite=None, diagnostics=None, client=None)
```

**Inputs:** config: path, mapping, or supported retrieval config. Optional non-None keyword overrides replace download/output/manifest/overwrite/diagnostic settings; client supplies a transport.

**Returns:** RetrievalRunResult with named results and single for a successful one-population run. Downloads/interpolates by configured defaults; failed runs raise RetrievalRunError carrying result.

**Also exported as:** `zju_scatt_interface.access.retrieve`.

### `interpolate`

Dispatch interpolation for homogeneous source objects.

```text
interpolate(sources, target, *, particle_type, **options)
```

**Inputs:** sources: nonempty sequence of OpticalNode or OpticalSourceRequest; target: coordinate mapping; particle_type: profile. Options follow the selected interpolation handler.

**Returns:** InterpolatedOpticalProduct with optics and interpolation provenance for built-ins; unsupported/mixed input types raise.

### `integrate`

Integrate a loaded physical optical slice over a PSD.

```text
integrate(
    optics: 'SingleParticleOptics',
    distribution: 'SizeDistribution',
    *,
    database_size_definition: 'Optional[str]' = None,
    geometry_converter: 'Optional[Callable]' = None,
    geometry_source: 'Optional[str]' = None,
    truncation_policy: 'str' = 'error',
) -> 'tuple[BulkOptics, RemapReport]'
```

**Inputs:** optics: SingleParticleOptics; distribution: SizeDistribution. Size-definition conversion requires justified geometry; truncation_policy controls uncovered bins.

**Returns:** (BulkOptics, RemapReport). Does not select/download sources.

**Also exported as:** `zju_scatt_interface.bulk.integrate`.

### `combine`

Combine extensive coefficients and re-derive intensive optical quantities.

```text
combine(
    results: 'Sequence[BulkOptics]',
    weights: 'Sequence[float] | None' = None,
    *,
    metadata: 'Mapping[str, object] | None' = None,
) -> 'BulkOptics'
```

**Inputs:** results: compatible BulkOptics sequence; weights: optional nonnegative population weights; metadata: explicit additional provenance.

**Returns:** BulkOptics; SSA, asymmetry and phases are derived with physical coefficient weighting.

**Also exported as:** `zju_scatt_interface.bulk.combine`.

### `compute_population`

Calculate one particle population at one wavelength, including ensemble diagnostics.

```text
compute_population(
    particle_type: 'str',
    source_paths: 'str | Path | Sequence[str | Path]',
    size_distribution: 'SizeDistribution',
    *,
    wavelength: 'object',
    wavelength_unit: 'str' = 'um',
    parameters: 'Mapping[str, object] | None' = None,
    shape_ensemble: 'WeightedShapeEnsemble | Sequence[WeightedShapeMember] | None' = None,
    refractive_index_tables: 'Mapping[str, object] | None' = None,
    size_definition: 'str | None' = None,
    truncation_policy: 'str' = 'error',
    include_phase_matrix: 'bool' = False,
    target_angles_degrees: 'Sequence[float] | None' = None,
    phase_normalization: 'str' = 'preserve',
    check_convergence: 'bool' = True,
    convergence_tolerance: 'float' = 0.05,
    strict_convergence: 'bool' = False,
    qa_tolerance: 'float' = 1e-08,
    strict_qa: 'bool' = True,
    uncertainty_metadata: 'Mapping[str, object] | None' = None,
) -> 'PopulationResult'
```

**Inputs:** particle_type, local source_paths and size_distribution are required, together with wavelength. parameters supplies profile coordinates/RI; shape_ensemble preserves joint states. Phase, size, truncation, QA and convergence keywords control explicit scientific policies.

**Returns:** PopulationResult: bulk optics, per-member remapping/QA/convergence/provenance and ensemble metadata. Invalid strict checks raise.

**Also exported as:** `zju_scatt_interface.bulk.compute_population`.

### `build`

Build the requested scheme/product type through a registered handler.

```text
build(scheme, *, plan=None, **options)
```

**Inputs:** scheme: ordinary scheme/path/mapping, SingleBulkScheme or MultiBulkScheme. Ordinary schemes accept plan=DependencyPlan; remaining options follow build_dataset. Grid schemes use source_paths and grid-build options instead of plan.

**Returns:** BulkDataset for an ordinary scheme; BulkGrid or MultiBulkGrid for retained grids. Returns data; call write to save. Incomplete plans refresh in their workspace, inheriting offline policy.

### `validate`

Validate a supported scientific input or saved product.

```text
validate(product, **options)
```

**Inputs:** product: Scheme, BulkOptics, or canonical bulk file path for built-ins. Options are forwarded to that type's validator. Load a scheme path before using this operation on its configuration.

**Returns:** Scheme -> dependency-query tuple; BulkOptics -> BulkQualityReport; file path -> OutputValidationReport. This is not one uniform report type.

### `read`

Read canonical NetCDF4/HDF5 output into an inspection mapping.

```text
read(path: 'Union[str, Path]', *, format: 'Optional[str]' = None) -> 'dict[str, object]'
```

**Inputs:** path: canonical bulk file; format: optional explicit netcdf4/hdf5 selector, otherwise inferred.

**Returns:** dict with attributes, datasets and named components; does not reconstruct calculation/result objects.

**Also exported as:** `zju_scatt_interface.io.read`.

### `write`

Write a supported product in a canonical format.

```text
write(product, path, *, wavelength_um=None, wavelengths_um=None, format=None, **options)
```

**Inputs:** product: dataset, grid, population, table result, bare BulkOptics or supported homogeneous sequence. path selects destination; format overrides suffix inference. Bare optics require wavelength_um; bare-optics sequences require wavelengths_um. Options include canonical OutputOptions/provenance where supported.

**Returns:** Destination Path for built-in writers; validates before atomic replacement by default. Existing destination can be replaced.

**Also exported as:** `zju_scatt_interface.io.write`.

### `plot`

Plot a typed product or explicitly identified file kind.

```text
plot(product, *, kind=None, **options)
```

**Inputs:** product: supported optics/bulk object or file. File paths require kind='single'/'bulk'; options follow plot_single_scattering or plot_bulk_optics.

**Returns:** Inspection/output mapping from the selected built-in plotter, including generated files and selection information. Writes plot artifacts; no optical recalculation.

<a id="functions-2"></a>
## zju_scatt_interface.access

### `register_direct`

Register through the service and save the session locally.

```text
register_direct(
    organization: 'str',
    country: 'str',
    *,
    consent: 'bool',
    name: 'Optional[str]' = None,
    email: 'Optional[str]' = None,
    intended_use: 'Optional[str]' = None,
    dataset_needs: 'Iterable[str]' = (),
    minimal: 'bool' = False,
    client: 'Optional[ApiClient]' = None,
) -> 'str'
```

**Inputs:** organization, country and explicit consent; optional researcher information, dataset needs, minimal mode and client. Supply the researcher's actual information.

**Returns:** Session token string (secret); also writes local session configuration. Never include this return in chat or shared reports.

### `load_session_token`

Resolve an existing session token.

```text
load_session_token(explicit: 'Optional[str]' = None) -> 'Optional[str]'
```

**Inputs:** explicit: optional token override; otherwise checks environment and local saved registration.

**Returns:** Token string or None (secret). Does not establish remote validity.

### `save_session_token`

Persist a token and optional registration metadata.

```text
save_session_token(token: 'str', metadata: 'Optional[dict]' = None) -> 'None'
```

**Inputs:** token: valid registered session secret; metadata: optional mapping for local storage.

**Returns:** None; writes local session configuration. Do not place secrets in a scientific input.

### `search_data`

Return the remote objects selected by a retrieval query.

```text
search_data(**parameters) -> 'list[RemoteObject]'
```

**Inputs:** parameters are forwarded to retrieve_sources, including client/transport options, sources or manifest, particle_types, wavelength/shape/RI selections and filters. download defaults to False; an explicitly supplied value is preserved. Normal registration is required by retrieve_sources. Optional manifest/log paths retain their normal effects.

**Returns:** list[RemoteObject], taken from RetrievalResult.objects. This convenience wrapper does not return the complete retrieval report or enforce its completion status; use retrieve_sources when those checks are needed.

### `estimate_data`

Return scan and storage statistics for a retrieval query.

```text
estimate_data(**parameters) -> 'ScanStats'
```

**Inputs:** parameters follow retrieve_sources, including sources or manifest, particle and scientific selectors, filters and client/transport options. download defaults to False; an explicitly supplied value is preserved. Normal registration is required by retrieve_sources. Optional manifest/log paths retain their normal effects.

**Returns:** ScanStats, taken from RetrievalResult.stats. This is the query's statistics record, not a download or numerical-build result; use retrieve_sources for the complete result and status.

### `retrieve_sources`

Select native sources with optional downloads/interpolation.

```text
retrieve_sources(
    *,
    client: 'Optional[ApiClient]' = None,
    timeout: 'float' = 30.0,
    retries: 'int' = 3,
    insecure: 'bool' = False,
    **parameters,
) -> 'RetrievalResult'
```

**Inputs:** client/timeout/retries/insecure control transport. parameters uses the retrieval keyword contract: particle_types, sources/manifest, target_wavelengths, shapes, target_temperatures, refractive_index_parameters, download, output_dir, apply_interpolation and filters.

**Returns:** RetrievalResult with selected objects, byte estimate, download records and derived products. Lower-level completion must be checked explicitly.

#### Forwarded retrieval keywords

The accepted `**parameters` names/defaults are shown below. This is
the argument contract used by the selector, not another recommended
research entry point. Target wavelengths trigger supported scientific
resolution; wavelength_range is a raw filename filter. File/count limits
must not truncate a required interpolation stencil. Session values are
secrets and should be supplied through local registration instead.

```text
retrieval_keywords(
    *,
    sources: 'Optional[Union[str, Sequence[str]]]' = None,
    manifest: 'Optional[Union[str, Path]]' = None,
    particle_types: 'Optional[Union[str, Sequence[str]]]' = None,
    wavelength_range: 'Optional[Sequence[Any]]' = None,
    wavelength_unit: 'str' = 'um',
    target_wavelengths: 'Optional[Union[Any, Sequence[Any]]]' = None,
    target_temperatures: 'Optional[Union[Any, Sequence[Any]]]' = None,
    target_wavelength_mode: 'str' = 'interp',
    target_tolerance_um: 'float' = 1e-09,
    refractive_index_parameters: 'Optional[Mapping[str, Mapping[str, Any]]]' = None,
    apply_interpolation: 'bool' = True,
    interpolation_output_dir: 'Optional[Union[str, Path]]' = None,
    interpolation_include_phase_matrix: 'bool' = False,
    ref_real_range: 'Optional[Sequence[Any]]' = None,
    ref_real_targets: 'Optional[Union[Any, Sequence[Any]]]' = None,
    ref_real_tolerance: 'float' = 1e-09,
    ref_imag_range: 'Optional[Sequence[Any]]' = None,
    ref_imag_targets: 'Optional[Union[Any, Sequence[Any]]]' = None,
    ref_imag_tolerance: 'float' = 1e-12,
    size_range: 'Optional[Sequence[Any]]' = None,
    target_sizes: 'Optional[Union[Any, Sequence[Any]]]' = None,
    target_size_tolerance: 'float' = 1e-09,
    shapes: 'Optional[Union[Mapping[str, Any], list[Mapping[str, Any]]]]' = None,
    contains: 'Optional[Union[str, Sequence[str]]]' = None,
    exclude: 'Optional[Union[str, Sequence[str]]]' = None,
    glob: 'Optional[Union[str, Sequence[str]]]' = None,
    exclude_glob: 'Optional[Union[str, Sequence[str]]]' = None,
    regex: 'Optional[Union[str, Sequence[str]]]' = None,
    ignore_case: 'bool' = True,
    extension: 'Optional[Union[str, Sequence[str]]]' = ('nc',),
    min_file_size: 'Optional[Union[int, str]]' = None,
    max_file_size: 'Optional[Union[int, str]]' = None,
    modified_after: 'Optional[Union[str, datetime]]' = None,
    modified_before: 'Optional[Union[str, datetime]]' = None,
    max_scan: 'Optional[int]' = None,
    quiet: 'bool' = True,
    download: 'bool' = False,
    output_dir: 'Optional[Union[str, Path]]' = None,
    workers: 'int' = 4,
    max_files: 'Optional[int]' = None,
    max_bytes: 'Optional[Union[int, str]]' = None,
    flat: 'bool' = False,
    overwrite: 'bool' = False,
    resume: 'bool' = True,
    verify_etag: 'bool' = False,
    ignore_space: 'bool' = False,
    no_progress: 'bool' = True,
    session: 'Optional[str]' = None,
    no_track: 'bool' = False,
    display_limit: 'int' = 200,
    urls: 'bool' = False,
    manifest_output: 'Optional[Union[str, Path]]' = None,
    operation_log: 'Optional[Union[str, Path]]' = None,
    manifest_format: 'Optional[str]' = None,
) -> 'argparse.Namespace'
```

### `load_retrieval_config`

Load configured retrieval inputs.

```text
load_retrieval_config(config)
```

**Inputs:** config: in-memory mapping, JSON path or trusted Python path defining retrieval.

**Returns:** Normalized retrieval configuration mapping; Python files execute code.

### `initialize_data_directory`

Create/select the default retrieval storage directory.

```text
initialize_data_directory(path='zju_scatt_data')
```

**Inputs:** path: local directory path.

**Returns:** Path; creates the directory and changes the current process's default retrieval destination.

<a id="functions-3"></a>
## zju_scatt_interface.bulk

### `integrate_arrays`

Integrate explicit optical arrays with a conservatively remapped PSD.

```text
integrate_arrays(
    distribution: 'SizeDistribution',
    database_size_um: 'Sequence[float]',
    *,
    database_size_definition: 'Optional[str]' = None,
    geometry_converter: 'Optional[Callable]' = None,
    geometry_source: 'Optional[str]' = None,
    truncation_policy: 'str' = 'error',
    extinction_cross_section_m2: 'Optional[Sequence[float]]' = None,
    scattering_cross_section_m2: 'Optional[Sequence[float]]' = None,
    absorption_cross_section_m2: 'Optional[Sequence[float]]' = None,
    extinction_efficiency: 'Optional[Sequence[float]]' = None,
    scattering_efficiency: 'Optional[Sequence[float]]' = None,
    absorption_efficiency: 'Optional[Sequence[float]]' = None,
    asymmetry_factor: 'Optional[Sequence[float]]' = None,
    phase_matrix: 'Optional[Sequence[object]]' = None,
    metadata: 'Optional[dict]' = None,
) -> 'tuple[BulkOptics, RemapReport]'
```

**Inputs:** distribution: typed PSD; database_size_um: source physical radius grid. Supply matching cross sections in m2 or supported efficiencies, optional asymmetry/phases, geometry policy and metadata.

**Returns:** (BulkOptics, RemapReport). Caller is responsible for physically consistent source arrays and metadata.

### `build_dataset`

Build every named component of an ordinary bulk scheme.

```text
build_dataset(
    config: 'object',
    *,
    source_paths: 'Mapping[str, str | Path | Sequence[str | Path]] | str | Path | Sequence[str | Path] | None' = None,
    dependency_plan: 'object | None' = None,
    workspace: 'str | Path' = 'zju_scatt_data',
    offline: 'bool' = False,
    include_phase_matrix: 'bool | None' = None,
    target_angles_degrees: 'Sequence[float] | None' = None,
    phase_normalization: 'str' = 'preserve',
    truncation_policy: 'str | None' = None,
    check_convergence: 'bool | None' = None,
    convergence_tolerance: 'float | None' = None,
    strict_convergence: 'bool | None' = None,
    strict_qa: 'bool | None' = None,
) -> 'BulkDataset'
```

**Inputs:** config: Scheme or supported scheme input. source_paths can override all component sources; dependency_plan is the specialist keyword. workspace/offline and scientific options control source preparation and repeated population calculations.

**Returns:** BulkDataset with independent components and retained dependency information. This specialist API differs from root build(plan=...).

### `build_table`

Build configured reference/override spectra and optional outputs.

```text
build_table(config, *, progress=<callback:_progress>)
```

**Inputs:** config: BulkTableConfig, mapping, JSON or trusted Python input defining bulk_table; progress: callback for progress messages.

**Returns:** BulkTableResult with rows, scheme and assumptions report. Writes configured output_dir formats if supplied.

### `load_table_config`

Read a table workflow configuration.

```text
load_table_config(path)
```

**Inputs:** path: JSON or trusted Python file defining bulk_table; relative paths resolve beside the input file.

**Returns:** BulkTableConfig; Python input executes code.

### `resolve_bulk_settings`

Inspect preset assumptions combined with particle overrides.

```text
resolve_bulk_settings(particle_type, overrides=None, *, preset='literature_v1')
```

**Inputs:** particle_type: profile; overrides: explicit mapping; preset: reference preset name.

**Returns:** Resolved settings mapping; performs no downloads or optical calculation.

### `build_grid`

Calculate every coordinate state of one retained grid.

```text
build_grid(
    scheme: 'SingleBulkScheme',
    *,
    source_paths: 'object' = None,
    include_phase_matrix: 'bool' = False,
    target_angles_degrees: 'Sequence[float] | None' = None,
    phase_normalization: 'str' = 'preserve',
    truncation_policy: 'str' = 'error',
    check_convergence: 'bool' = True,
    convergence_tolerance: 'float' = 0.05,
    strict_convergence: 'bool' = False,
    strict_qa: 'bool' = True,
) -> 'BulkGrid'
```

**Inputs:** scheme: SingleBulkScheme; source_paths: explicit local sources. Remaining keywords select phase, truncation, convergence and QA policies.

**Returns:** BulkGrid with retained dimensions and population calculations; no cross-state averaging.

### `build_grids`

Calculate independent retained grids for several populations.

```text
build_grids(
    scheme: 'MultiBulkScheme',
    *,
    source_paths: 'Mapping[str, object] | object' = None,
    **kwargs: 'object',
) -> 'MultiBulkGrid'
```

**Inputs:** scheme: MultiBulkScheme; source_paths: local sources by name/type or supported shared source input. kwargs follow build_grid.

**Returns:** MultiBulkGrid; populations are not implicitly mixed.

### `load_grid_scheme`

Load retained-grid definitions from a Python configuration.

```text
load_grid_scheme(path: 'str | Path') -> 'MultiBulkScheme'
```

**Inputs:** path: trusted Python file defining multi_bulk_scheme.

**Returns:** MultiBulkScheme; loading executes the Python file.

<a id="functions-4"></a>
## zju_scatt_interface.config

### `list_particle_profiles`

List registered particle contracts.

```text
list_particle_profiles() -> 'Tuple[ParticleProfile, ...]'
```

**Inputs:** No arguments.

**Returns:** Tuple of ParticleProfile values, including registered extensions.

### `scheme_reference`

Inspect the machine-readable domain/command contract.

```text
scheme_reference(particle_type: 'Optional[str]' = None) -> 'dict[str, object]'
```

**Inputs:** particle_type: optional profile filter.

**Returns:** dict containing scheme fields, units, profile metadata and command templates; not a generic JSON Schema or availability check.

### `write_scheme_reference`

Save the machine-readable reference.

```text
write_scheme_reference(path: 'Union[str, Path]', *, particle_type: 'Optional[str]' = None) -> 'Path'
```

**Inputs:** path: JSON destination; particle_type: optional profile filter.

**Returns:** Path; writes deterministic reference JSON.

<a id="functions-5"></a>
## zju_scatt_interface.extensions

### `register_particle`

Register a complete particle extension contract.

```text
register_particle(definition: 'ParticleDefinition')
```

**Inputs:** definition: ParticleDefinition with profile, native axes and required callbacks.

**Returns:** Registered ParticleDefinition; conflicting names/aliases or invalid callbacks raise ExtensionError.

### `get_particle_definition`

Look up a registered particle implementation contract.

```text
get_particle_definition(name)
```

**Inputs:** name: canonical particle name or alias.

**Returns:** ParticleDefinition; unknown name raises ExtensionError.

### `register_operation`

Register a type-specific public operation handler.

```text
register_operation(operation, product_type, handler)
```

**Inputs:** operation: supported operation name; product_type: dispatch class; handler: callable receiving product and operation options (plus path for write).

**Returns:** Registered handler callable; rejects duplicate type bindings or unsupported operation names.

### `register_plotter`

Register an explicit plot kind.

```text
register_plotter(kind, handler)
```

**Inputs:** kind: unique name; handler: callable receiving product and plot options.

**Returns:** Registered handler callable; rejects conflicts and noncallable handlers.

### `create_psd`

Create a PSD through a registered named factory.

```text
create_psd(config, context: PSDContext)
```

**Inputs:** config: mapping containing type and factory-specific settings; context: PSDContext with physical support and concentration.

**Returns:** SizeDistribution; rejects factories returning an incompatible type.

### `register_psd`

Add a named analytical/custom PSD factory.

```text
register_psd(name, factory: PSDFactory, *, aliases=())
```

**Inputs:** name, PSDFactory and optional aliases.

**Returns:** Registered PSDFactory; does not create a PSD or perform a calculation.

### `register_exporter`

Add a named application exporter.

```text
register_exporter(name, exporter: 'Exporter', *, aliases=())
```

**Inputs:** name, Exporter(write, optional validate), and aliases.

**Returns:** Registered Exporter contract; does not write files at registration time.

### `export`

Invoke a registered application writer.

```text
export(application, data, destination, **options)
```

**Inputs:** application: exporter name; data: supported product; destination: exporter-specific path/directory; options follow that writer.

**Returns:** The selected exporter's result (built-ins return manifest mappings); creates application outputs.

### `validate_export`

Invoke a registered application validator.

```text
validate_export(application, path, **options)
```

**Inputs:** application: exporter name; path: written product; options follow the validator.

**Returns:** Validator result mapping for supported built-ins; raises when no validator is registered.

### `register_command`

Register a CLI command before constructing the parser.

```text
register_command(command: 'Command')
```

**Inputs:** command: Command with name/help, configure and run callbacks, plus optional validate.

**Returns:** Registered Command; built-in name collisions are rejected.

### `register_native_model`

Register model-specific native array/template policies.

```text
register_native_model(name, model: 'NativeModel', *, aliases=())
```

**Inputs:** name, NativeModel with required validate callback and optional read/template/phase/field callbacks; aliases.

**Returns:** Registered NativeModel contract.

### `register_serializer`

Register a native serialization backend.

```text
register_serializer(name, serialize, *, aliases=())
```

**Inputs:** name, serialize(temporary_path, arrays, template) callback and optional aliases.

**Returns:** Registered serializer callable. The callback must write exactly the supplied temporary file.

<a id="functions-6"></a>
## zju_scatt_interface.io

### `validate_file`

Validate a canonical saved bulk product.

```text
validate_file(path: 'Union[str, Path]', *, format: 'Optional[str]' = None) -> 'OutputValidationReport'
```

**Inputs:** path and optional explicit format.

**Returns:** OutputValidationReport; require_valid() raises if its checks fail. Does not perform source/PSD convergence analysis.

### `write_formatted_optical_output`

Render a canonical product as a configured text table.

```text
write_formatted_optical_output(
    path: 'Union[str, Path]',
    data: 'DataInput',
    format_spec: 'FormatInput',
    *,
    encoding: 'str' = 'utf-8',
) -> 'Union[Path, tuple[Path, ...]]'
```

**Inputs:** path: destination/stem; data: supported result, canonical mapping or file; format_spec: OpticalTableFormat/mapping/specification input; encoding.

**Returns:** Path or tuple of Paths for component-split output. Uses explicit column scale/transform conventions.

### `load_optical_table_format`

Load a text-table formatting contract.

```text
load_optical_table_format(path: 'Union[str, Path]') -> 'OpticalTableFormat'
```

**Inputs:** path: JSON or trusted Python specification defining optical_table_format.

**Returns:** OpticalTableFormat; Python specifications execute code.

### `export_bulk_optics`

Write custom NetCDF/HDF5 layouts without recalculating optics.

```text
export_bulk_optics(data, output, *, output_dir=None, overwrite=False)
```

**Inputs:** data: supported bulk result/grid/mapping/canonical file. output: layout mapping, outputs collection or trusted Python/JSON config. output_dir selects base; overwrite controls existing custom files.

**Returns:** dict with outputs and per-file results/validation. Rejects canonical-source overwrite and unsupported/lossy conversions.

<a id="functions-7"></a>
## zju_scatt_interface.io.applications

### `write_rttov13_bulk_tables`

Export fixed-PSD RTTOV13-style aerosol/cloud tables.

```text
write_rttov13_bulk_tables(
    result,
    directory,
    *,
    max_moments=32,
    water_density_kg_m3=1000.0,
    ice_density_kg_m3=917.0,
    phase_normalization='preserve',
)
```

**Inputs:** result: supported complete spectrum; directory: destination; moment count, material densities and phase normalization must match the scientific contract.

**Returns:** Manifest mapping and files. High-level descriptive/ZJU cloud names require reader adaptation.

**Also exported as:** `zju_scatt_interface.io.applications.rttov.write_rttov13_bulk_tables`.

### `write_rttov14_bulk_tables`

Export fixed-population RTTOV14 version-4 tables.

```text
write_rttov14_bulk_tables(
    data,
    directory,
    *,
    max_moments=32,
    water_density_kg_m3=1000.0,
    ice_density_kg_m3=917.0,
    phase_normalization='preserve',
)
```

**Inputs:** data: supported table result or canonical file with required sibling report.json; directory; moment/density/phase settings.

**Returns:** Manifest mapping and aertable/hydrotable files for the implemented thermal-IR subset.

**Also exported as:** `zju_scatt_interface.io.applications.rttov.write_rttov14_bulk_tables`.

### `validate_rttov14_optical_table`

Validate the fixed-population RTTOV14 output subset.

```text
validate_rttov14_optical_table(path)
```

**Inputs:** path: emitted version-4 NetCDF optical table.

**Returns:** Validation mapping; checks source-schema/physical invariants, not a compiled simulation.

### `build_rttov14_lookup_tables`

Compute retained size/RH/temperature RTTOV14 master tables.

```text
build_rttov14_lookup_tables(
    *,
    wavelengths,
    source_paths,
    effective_radii_um,
    relative_humidity_percent,
    ice_temperatures_k,
    output_dir,
    bins=160,
    max_moments=32,
    sea_salt_branch='deliquescence',
    overrides=None,
    progress=<built-in function print>,
)
```

**Inputs:** wavelengths, local source_paths, effective_radii_um, relative_humidity_percent, ice_temperatures_k and output_dir are explicit. bins/moments, branch, overrides and progress control calculation.

**Returns:** Manifest mapping and master table files. RH here is explicitly percent. Requires downstream slicing/adaptation where stock axes differ.

**Also exported as:** `zju_scatt_interface.io.applications.rttov.build_rttov14_lookup_tables`.

### `write_rttov14_lookup_slice`

Select exact master-grid states for supported stock runtime axes.

```text
write_rttov14_lookup_slice(master_path, output_path, *, aerosol_effective_radii_um=None, ice_temperature_k=220.0)
```

**Inputs:** master_path, output_path; aerosol_effective_radii_um and ice_temperature_k select exact nodes.

**Returns:** Lookup validation mapping; writes output_path without inventing interpolated states.

**Also exported as:** `zju_scatt_interface.io.applications.rttov.write_rttov14_lookup_slice`.

### `validate_rttov14_lookup_table`

Validate a retained/sliced RTTOV14 lookup table.

```text
validate_rttov14_lookup_table(path)
```

**Inputs:** path: lookup NetCDF file.

**Returns:** Validation mapping for the implemented lookup schema; distinct from the fixed-population validator.

### `rename_rttov14_species`

Copy a table with explicit particle names.

```text
rename_rttov14_species(source, destination, output_names)
```

**Inputs:** source, destination, output_names mapping/sequence as accepted by the table naming contract.

**Returns:** Mapping identifying output/names; writes a copy while preserving optical arrays.

**Also exported as:** `zju_scatt_interface.io.applications.rttov.rename_rttov14_species`.

### `write_arts_bulk_tables`

Export totally-random ARTS version-3 SSD XML for fixed PSDs.

```text
write_arts_bulk_tables(data, output_dir, *, reference_temperature_k=273.15, phase_normalization='error')
```

**Inputs:** data, output_dir, reference_temperature_k and phase_normalization. Requires complete six-element phase data and concentration metadata.

**Returns:** Manifest mapping and one effective SSD XML product per supported population.

**Also exported as:** `zju_scatt_interface.io.applications.arts.write_arts_bulk_tables`.

### `validate_arts_bulk_table`

Validate an emitted ARTS SSD tensor product.

```text
validate_arts_bulk_table(path, *, normalization_tolerance=0.01)
```

**Inputs:** path and normalization_tolerance for integrated Z11 closure.

**Returns:** Validation mapping; unsupported schema/normalization raises.

**Also exported as:** `zju_scatt_interface.io.applications.arts.validate_arts_bulk_table`.

### `write_crtm_ir_bulk_tables`

Export the implemented CRTM IR fixed-population subset.

```text
write_crtm_ir_bulk_tables(
    data,
    output_dir,
    *,
    material_densities_kg_m3,
    growth_factors=None,
    phase_normalization='error',
)
```

**Inputs:** data, output_dir and material_densities_kg_m3; optional growth_factors and phase_normalization.

**Returns:** Manifest mapping and IR table files; does not create a complete arbitrary native CRTM CloudCoeff dataset.

**Also exported as:** `zju_scatt_interface.io.applications.crtm.write_crtm_ir_bulk_tables`.

### `validate_crtm_ir_optical_table`

Check the emitted CRTM IR subset.

```text
validate_crtm_ir_optical_table(path)
```

**Inputs:** path: emitted IR table.

**Returns:** dict including valid and native_crtm_compatible=False; does not claim native compiled-reader acceptance.

**Also exported as:** `zju_scatt_interface.io.applications.crtm.validate_crtm_ir_optical_table`.

<a id="functions-8"></a>
## zju_scatt_interface.optics

### `load_single`

Load one physical optical slice from a native file.

```text
load_single(
    path: 'Union[str, Path]',
    *,
    include_phase_matrix: 'bool' = False,
    size_dataset: 'Optional[str]' = None,
    coordinate_indices: 'Optional[Mapping[str, int]]' = None,
    cext_mode: 'str' = 'auto',
    wavelength_um: 'Optional[float]' = None,
    allow_nan_asymmetry: 'bool' = False,
) -> 'SingleParticleOptics'
```

**Inputs:** path; include_phase_matrix; size_dataset and coordinate_indices for native axes; cext_mode and wavelength_um for physical interpretation; explicit NaN-asymmetry policy.

**Returns:** SingleParticleOptics in physical units for the selected slice; does not preserve every native variable as a generic file reader.

### `interpolate_nodes`

Interpolate already-loaded optical nodes within supported coordinates.

```text
interpolate_nodes(
    particle_type: 'str',
    nodes: 'Sequence[OpticalNode]',
    target_coordinates: 'Mapping[str, float | str]',
    *,
    target_size_um: 'Sequence[float] | None' = None,
    target_angles_degrees: 'Sequence[float] | None' = None,
    sparse_power: 'float' = 2.0,
    phase_normalization: 'str' = 'preserve',
) -> 'InterpolatedOpticalProduct'
```

**Inputs:** particle_type, OpticalNode sequence, target_coordinates; optional output size/angle grids, sparse-power and phase-normalization policy.

**Returns:** InterpolatedOpticalProduct with physical optics and neighbor provenance.

### `interpolate_sources`

Load local source requests and interpolate physical optics.

```text
interpolate_sources(
    particle_type: 'str',
    sources: 'Sequence[OpticalSourceRequest]',
    target_coordinates: 'Mapping[str, float | str]',
    **kwargs: 'Any',
) -> 'InterpolatedOpticalProduct'
```

**Inputs:** particle_type, OpticalSourceRequest sequence and target_coordinates; kwargs follow interpolate_nodes.

**Returns:** InterpolatedOpticalProduct; invalid/incompatible source support raises.

### `default_refractive_index_paths`

Locate packaged material tables for a profile/scheme.

```text
default_refractive_index_paths(particle_type: 'str', *, ri_scheme: 'str' = 'v1.2.1') -> 'Mapping[str, Path]'
```

**Inputs:** particle_type and explicit/default ri_scheme.

**Returns:** Mapping from material role to Path; location is not proof the target has covered source optics.

### `wavelength_to_um`

Convert wavelength/wavenumber to positive micrometres.

```text
wavelength_to_um(value: 'object', unit: 'str' = 'um') -> 'float'
```

**Inputs:** value: supported scalar input; unit: um, nm or cm-1.

**Returns:** float in um; invalid/nonpositive inputs raise.

<a id="functions-9"></a>
## zju_scatt_interface.optics.retrieval

### `interpolate_downloaded_particle_series`

Write native-schema derived files from selected downloads.

```text
interpolate_downloaded_particle_series(
    downloaded_sources,
    targets,
    processing,
    output_dir,
    *,
    include_phase_matrix=False,
    overwrite=False,
    tolerance_um=1e-09,
    progress=None,
)
```

**Inputs:** downloaded_sources, targets and processing records from retrieval; output_dir; overwrite/tolerance/progress and phase-compatibility controls.

**Returns:** List of InterpolatedFileResult records; writes derived products while preserving native source schemas. Prefer configured retrieve for ordinary use.

### `verify_native_schema`

Compare a derived native file to its template schema.

```text
verify_native_schema(path, template_path)
```

**Inputs:** path: derived file; template_path: authoritative source template.

**Returns:** bool indicating complete compatible dimensions, variables, dtypes and variable attributes; reads files.

<a id="functions-10"></a>
## zju_scatt_interface.plotting

### `plot_single_particle_optics`

Create live single-particle scalar and phase figures.

```text
plot_single_particle_optics(
    optics,
    *,
    output=None,
    phase_output=None,
    phase_radii_um=None,
    title=None,
    show=False,
    dpi=300,
    style=None,
)
```

**Inputs:** optics: loaded SingleParticleOptics; optional scalar/phase output paths, selected radii, title, show, dpi and style.

**Returns:** Figure mapping with properties/phase entries; requested paths save figures.

### `plot_single_scattering`

Inspect a single-particle file or loaded slice with outputs.

```text
plot_single_scattering(
    source,
    *,
    output_dir=None,
    wavelength_um=None,
    coordinate_indices=None,
    show=False,
    style=None,
)
```

**Inputs:** source: file or SingleParticleOptics; output_dir/style/show; wavelength_um and coordinate_indices apply to file loading.

**Returns:** dict with output_dir, files and inspection; writes figures, CSV and inspection report.

### `plot_bulk_optics`

Inspect existing bulk products without recalculation.

```text
plot_bulk_optics(source, *, output_dir=None, show=False, style=None)
```

**Inputs:** source: supported canonical file/mapping/grid/optics; output_dir, show and style.

**Returns:** dict with files, report_file, figures and inspection, including fixed/varying axis selections.

<a id="functions-11"></a>
## zju_scatt_interface.psd

### `lognormal_psd`

Construct CDF-integrated lognormal bin counts.

```text
lognormal_psd(
    rg_um,
    sigma_g,
    number_concentration_cm3=1.0,
    *,
    radius_range_um=None,
    bins=400,
    normalization='preserve',
)
```

**Inputs:** rg_um: geometric mean radius; sigma_g: geometric standard deviation; concentration; finite radius_range_um, bins and preserve/renormalize policy.

**Returns:** SizeDistribution on volume-equivalent radii with probability/realized-moment metadata.

### `gamma_psd`

Construct CDF-integrated gamma bin counts.

```text
gamma_psd(
    effective_radius_um,
    effective_variance,
    number_concentration_cm3=1.0,
    *,
    radius_range_um=None,
    bins=400,
    normalization='preserve',
)
```

**Inputs:** effective_radius_um=M3/M2; effective_variance between 0 and 0.5; concentration, finite bounds, bins and normalization policy.

**Returns:** SizeDistribution with represented-bin counts and parent/realized metadata.

### `check_size_coverage`

Inspect common physical support of a population/PSD.

```text
check_size_coverage(
    particle_type,
    source_paths,
    size_distribution,
    *,
    wavelength,
    wavelength_unit='um',
    parameters=None,
    shape_ensemble=None,
    refractive_index_tables=None,
    size_definition=None,
    truncation_policy='error',
)
```

**Inputs:** particle_type, local source_paths, typed PSD, wavelength/unit and profile/ensemble/RI/size-definition inputs; truncation_policy.

**Returns:** JSON-compatible mapping with source/common radius bounds, bin coverage, retained/lost concentration and policy.

<a id="functions-12"></a>
## zju_scatt_interface.sources

### `prepare_scheme_dependencies`

Prepare source queries, downloads and verified manifests.

```text
prepare_scheme_dependencies(
    config: 'Scheme',
    *,
    workspace: 'Union[str, Path]' = WindowsPath('zju_scatt_data'),
    offline: 'bool' = False,
    download: 'bool' = True,
    validate_schema: 'bool' = True,
    client: 'Optional[_domain_access_client.ApiClient]' = None,
    session: 'Optional[str]' = None,
    no_track: 'bool' = False,
    resume: 'bool' = True,
    searcher: 'Optional[SearchFunction]' = None,
    downloader: 'Optional[DownloadFunction]' = None,
    reuse_dirs: 'Sequence[Union[str, Path]]' = (),
) -> 'DependencyPlan'
```

**Inputs:** config: Scheme; workspace, offline and download (default True), schema-validation/session/transfer controls; optional custom searcher/downloader and reuse directories.

**Returns:** DependencyPlan with readiness/issues and manifest paths. Can download by default; use root plan or download=False for previews.

### `build_dependency_queries`

Compile deterministic queries from named scheme populations.

```text
build_dependency_queries(config: 'Scheme') -> 'Tuple[DependencyQuery, ...]'
```

**Inputs:** config: normalized Scheme.

**Returns:** Tuple of DependencyQuery records; compilation does not prove remote availability.

### `select_shape_grid_sources`

Select joint shape/RI source stencils without mixing revisions.

```text
select_shape_grid_sources(objects, family, points, targets)
```

**Inputs:** objects: catalog records; family: particle family; points: resolved RI targets; targets: shape targets.

**Returns:** (selected objects, resolution-record tuple, interpolation-required bool). Specialist selection stage; no numerical integration.

### `inspect_source_file`

Check native source identity and required variables.

```text
inspect_source_file(path: 'Union[str, Path]', particle_type: 'Union[str, ParticleProfile]') -> 'SourceInspection'
```

**Inputs:** path: local L1 file; particle_type: profile name or ParticleProfile.

**Returns:** SourceInspection with validation result, issues and source metadata.

<a id="functions-13"></a>
## zju_scatt_interface.sources.adapters

### `get_particle_adapter`

Instantiate the selected registered particle adapter.

```text
get_particle_adapter(particle_type: 'str') -> 'ParticleAdapter'
```

**Inputs:** particle_type: name/alias.

**Returns:** ParticleAdapter implementing resolution/interpolation capabilities.

### `resolve_particle_sources`

Resolve local particle files to minimal native source nodes.

```text
resolve_particle_sources(
    particle_type: 'str',
    source_paths: 'str | Path | Sequence[str | Path]',
    **kwargs: 'Any',
) -> 'AdapterResolution'
```

**Inputs:** particle_type, local source_paths; kwargs include wavelength/unit, parameters, RI tables, size definition and phase loading requirements.

**Returns:** AdapterResolution with target coordinates, selected source nodes and provenance.

### `resolve_plan_component_sources`

Resolve one named population from a verified dependency plan.

```text
resolve_plan_component_sources(plan: 'object', component_name: 'str', **kwargs: 'Any') -> 'AdapterResolution'
```

**Inputs:** plan: DependencyPlan; component_name: saved population name; kwargs supply adapter-resolution inputs.

**Returns:** AdapterResolution for that component; absent/unready source information raises.

### `interpolate_particle`

Resolve, load and interpolate one particle-family request.

```text
interpolate_particle(
    particle_type: 'str',
    source_paths: 'str | Path | Sequence[str | Path]',
    *,
    target_size_um: 'Sequence[float] | None' = None,
    target_angles_degrees: 'Sequence[float] | None' = None,
    phase_normalization: 'str' = 'preserve',
    **kwargs: 'Any',
) -> 'InterpolatedOpticalProduct'
```

**Inputs:** particle_type, local source_paths, optional output size/angle grids and phase policy; kwargs provide wavelength, parameters, RI tables and size definition.

**Returns:** InterpolatedOpticalProduct with physical optical values and adapter provenance.

<a id="functions-14"></a>
## zju_scatt_interface.io.native

### `load_native_output_template`

Read an explicit native-output JSON template.

```text
load_native_output_template(path)
```

**Inputs:** path: JSON template file.

**Returns:** Template mapping; reading is separate from model-array validation.

### `native_template_from_reference`

Inspect a supported reference file's native layout.

```text
native_template_from_reference(path, *, model)
```

**Inputs:** path: reference file; model: registered native model identifier.

**Returns:** Template mapping from the model's supported inspection callback.

### `read_native_optical_arrays`

Read arrays from a supported native model file.

```text
read_native_optical_arrays(path, *, model)
```

**Inputs:** path and registered model identifier.

**Returns:** Model-specific array mapping; unsupported read capability raises.

### `arts_output_template`

Construct a totally-random ARTS SSD template.

```text
arts_output_template(n_frequency, n_temperature, n_angle)
```

**Inputs:** n_frequency, n_temperature, n_angle: required axis lengths.

**Returns:** Template mapping; optical arrays must be supplied separately.

### `write_native_optical_output`

Serialize explicitly supplied arrays against a native/custom template.

```text
write_native_optical_output(path, data, template, *, overwrite=False)
```

**Inputs:** path: destination; data: array mapping; template: supported template input; overwrite controls replacement.

**Returns:** Path; validates/serializes to a temporary file before replacement. Does not compute absent physics.

### `crtm_cloud_output_template`

Construct the full release-3 CRTM CloudCoeff layout.

```text
crtm_cloud_output_template(dimensions, *, binary=False, byte_order='little', version=1)
```

**Inputs:** dimensions: explicit model dimension mapping; binary selects format; byte_order and version set binary/release fields.

**Returns:** Template mapping requiring the complete prescribed arrays, distinct from the high-level IR subset.

### `rttov13_aerosol_output_template`

Construct a RTTOV13 aerosol HDF5 template.

```text
rttov13_aerosol_output_template(
    n_channels,
    species,
    *,
    max_moments=128,
    phase_angles=(),
    solar_channels=(),
    species_naming='rttov',
)
```

**Inputs:** n_channels and species; moment count, optional phase angles/solar channels and explicit naming convention.

**Returns:** Template mapping; callers supply arrays in the correct sensor-channel order.

### `arts_arrays_from_bulk`

Convert a canonical population to ARTS-normalized arrays.

```text
arts_arrays_from_bulk(data, *, component, number_density_m3, temperature_k=None)
```

**Inputs:** data and selected component; number_density_m3 is explicit; temperature_k supplies the effective-state temperature when needed.

**Returns:** Array mapping with ARTS frequencies, tensors and normalization; requires complete phase information.

### `bulk_model_fields`

Convert bulk coefficients to a native model's concentration convention.

```text
bulk_model_fields(bulk, *, model, mass_concentration_kg_m3=None, number_density_m3=None)
```

**Inputs:** bulk: BulkOptics; model: registered policy; explicit mass_concentration_kg_m3 or number_density_m3 as required.

**Returns:** Model-specific optical-field mapping; missing normalization inputs raise.

### `scalar_phase_to_model`

Project scalar P11 into a model's phase representation.

```text
scalar_phase_to_model(
    angles_degrees,
    p11,
    *,
    model,
    max_moments=128,
    quadrature_points=512,
    hemisphere_points=32,
    normalization_tolerance=0.01,
)
```

**Inputs:** angles_degrees and p11; model, max_moments, quadrature/hemisphere resolution and normalization tolerance.

**Returns:** Model-specific phase/BPR/coefficient mapping. Does not generate missing vector generalized-spherical coefficients.

<a id="functions-15"></a>
## zju_scatt_interface.bulk.defaults

### `default_bulk_assumptions`

Resolve editable built-in/extension reference assumptions.

```text
default_bulk_assumptions(particle_type, source_paths=None, *, preset='literature_v1')
```

**Inputs:** particle_type, optional local source_paths, and preset name.

**Returns:** Settings mapping with shape/environment/PSD assumptions and resolved support-dependent defaults where available.

<a id="functions-16"></a>
## zju_scatt_interface.psd.analytical

### `radius_moments`

Measure realized radius moments of represented bin counts.

```text
radius_moments(psd)
```

**Inputs:** psd: SizeDistribution on the intended physical radius definition.

**Returns:** Mapping with number-mean radius, effective radius/variance and realized moment information.

### `gamma_radius_bounds`

Compute finite gamma radius bounds from parent parameters.

```text
gamma_radius_bounds(effective_radius_um, effective_variance)
```

**Inputs:** effective_radius_um and effective_variance.

**Returns:** (lower_um, upper_um), based on the implemented tail-probability cutoffs; not source coverage.

## Types and object methods

Constructor parameters below define the public fields/options. Constructors
return an instance of the named type; most result types are normally obtained
from operations rather than assembled by hand. Fields are not extra calls.

### `Scheme`

**Import:** `zju_scatt_interface.Scheme`.

Complete typed request for a multi-particle optical scheme.

```text
Scheme(
    name: 'str',
    wavelengths_um: 'tuple[float, ...]',
    particles: 'tuple[ParticleComponent, ...]',
    temperatures_k: 'tuple[float, ...]' = (),
    interpolation: 'str' = 'linear',
    output: 'str' = 'bulk_optical_scheme.nc',
    schema_version: 'str' = '1.0',
    output_settings: 'Optional[SchemeOutput]' = None,
    include_phase_matrix: 'bool' = False,
    scattering_angles_degrees: 'tuple[float, ...]' = (),
    truncation_policy: 'str' = 'error',
    check_convergence: 'bool' = True,
    convergence_tolerance: 'float' = 0.05,
    strict_convergence: 'bool' = False,
    strict_qa: 'bool' = True,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `Scheme` instance.

#### `Scheme.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(value: 'Mapping[str, Any]', *, base_dir: 'Union[str, Path, None]' = None) -> "'Scheme'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** Scheme or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `Scheme.from_dict`

Construct/normalize this type from a supported representation.

```text
from_dict(value: 'Mapping[str, Any]', *, base_dir: 'Union[str, Path, None]' = None) -> "'Scheme'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** Scheme or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `Scheme.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

#### `Scheme.write_json`

Save this object's JSON representation.

```text
write_json(self, path: 'Union[str, Path]', *, indent: 'int' = 2) -> 'Path'
```

**Inputs:** path: destination; indent: formatting control.

**Returns:** Path; writes a file, without recalculating optics.

#### `Scheme.validate`

Validate this existing scheme.

```text
validate(self) -> 'tuple[object, ...]'
```

**Inputs:** The existing Scheme; kwargs, where present, follows the corresponding root operation.

**Returns:** Tuple of validated dependency queries; does not prove source availability.

#### `Scheme.plan`

Plan this existing scheme.

```text
plan(self, **kwargs: 'object') -> 'object'
```

**Inputs:** The existing Scheme; kwargs, where present, follows the corresponding root operation.

**Returns:** DependencyPlan; may inspect remote listings and write manifests, but never downloads optical files.

#### `Scheme.build`

Build this existing scheme.

```text
build(self, **kwargs: 'object') -> 'object'
```

**Inputs:** The existing Scheme; kwargs, where present, follows the corresponding root operation.

**Returns:** BulkDataset; kwargs accepts plan= and supported build options; call write to save.

### `SizeDistribution`

**Import:** `zju_scatt_interface.SizeDistribution`.

Discrete per-bin particle concentrations on a physical radius grid.

```text
SizeDistribution(
    size: 'object',
    dndr: 'object',
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    *,
    dndr_unit: 'str' = 'cm-3',
    integration_mode: 'str' = 'discrete_bin',
    source: 'str' = 'python_array',
    metadata: 'Optional[Mapping[str, object]]' = None,
    gap_policy: 'str' = 'warn',
    maximum_log_spacing_ratio: 'float' = 10.0,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SizeDistribution` instance.

#### `SizeDistribution.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

#### `SizeDistribution.to_csv`

Write represented radii and bin counts with PSD metadata.

```text
to_csv(self, path: 'Union[str, Path]') -> 'Path'
```

**Inputs:** path: CSV destination.

**Returns:** Path; input concentration is retained.

#### `SizeDistribution.normalized`

Create an explicitly concentration-rescaled PSD.

```text
normalized(self, number_concentration_cm3: 'object') -> "'SizeDistribution'"
```

**Inputs:** number_concentration_cm3: requested represented concentration.

**Returns:** New SizeDistribution; source coordinate interpretation is preserved.

#### `SizeDistribution.remap`

Conservatively remap counts to another size grid.

```text
remap(
    self,
    target_size: 'object',
    *,
    target_size_unit: 'str' = 'um',
    truncation_policy: 'str' = 'error',
    outside_tolerance: 'float' = 1e-12,
) -> "tuple['SizeDistribution', RemapReport]"
```

**Inputs:** target_size/unit, explicit truncation policy and outside tolerance.

**Returns:** (SizeDistribution, RemapReport) with retained/lost concentration.

#### `SizeDistribution.convert_size_definition`

Convert PSD radii using verified geometry.

```text
convert_size_definition(
    self,
    target_definition: 'str',
    *,
    converter: 'Optional[Callable[[Tuple[float, ...]], Sequence[float]]]' = None,
    geometry_source: 'Optional[str]' = None,
) -> "'SizeDistribution'"
```

**Inputs:** target_definition; converter callback and geometry_source when a conversion is needed.

**Returns:** New SizeDistribution with recorded geometry; no universal radius-conversion factor is assumed.

#### `SizeDistribution.from_callable`

Evaluate a function as represented-bin values on explicit size coordinates.

```text
from_callable(
    size: 'object',
    function: 'Callable[[float], object]',
    *,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    source: 'Optional[str]' = None,
    **kwargs: 'object',
) -> "'SizeDistribution'"
```

**Inputs:** size and function(radius); unit/size definition/source and PSD options. Integrate a differential density into bin counts beforehand.

**Returns:** SizeDistribution; does not infer measurement-bin integrals.

#### `SizeDistribution.from_delimited`

Load a PSD with explicit coordinate/count conventions.

```text
from_delimited(
    path: 'Union[str, Path]',
    *,
    size_column: 'Optional[str]' = None,
    dndr_column: 'Optional[str]' = None,
    size_unit: 'str' = 'um',
    size_definition: 'Optional[str]' = None,
    delimiter: 'Optional[str]' = None,
    **kwargs: 'object',
) -> "'SizeDistribution'"
```

**Inputs:** path and optional field names, size unit/definition, count units and parsing options shown in the signature.

**Returns:** SizeDistribution; does not silently normalize measured counts.

#### `SizeDistribution.from_netcdf`

Load a PSD with explicit coordinate/count conventions.

```text
from_netcdf(
    path: 'Union[str, Path]',
    *,
    size_variable: 'str' = 'size',
    dndr_variable: 'str' = 'dndr',
    size_unit: 'Optional[str]' = None,
    size_definition: 'Optional[str]' = None,
    dndr_unit: 'Optional[str]' = None,
    **kwargs: 'object',
) -> "'SizeDistribution'"
```

**Inputs:** path and optional field names, size unit/definition, count units and parsing options shown in the signature.

**Returns:** SizeDistribution; does not silently normalize measured counts.

#### `SizeDistribution.from_hdf5`

Load a PSD with explicit coordinate/count conventions.

```text
from_hdf5(
    path: 'Union[str, Path]',
    *,
    size_dataset: 'str' = 'size',
    dndr_dataset: 'str' = 'dndr',
    size_unit: 'Optional[str]' = None,
    size_definition: 'Optional[str]' = None,
    dndr_unit: 'Optional[str]' = None,
    **kwargs: 'object',
) -> "'SizeDistribution'"
```

**Inputs:** path and optional field names, size unit/definition, count units and parsing options shown in the signature.

**Returns:** SizeDistribution; does not silently normalize measured counts.

#### `SizeDistribution.from_file`

Load a PSD with explicit coordinate/count conventions.

```text
from_file(path: 'Union[str, Path]', **kwargs: 'object') -> "'SizeDistribution'"
```

**Inputs:** path and optional field names, size unit/definition, count units and parsing options shown in the signature.

**Returns:** SizeDistribution; does not silently normalize measured counts.

#### `SizeDistribution.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(
    value: 'Mapping[str, object]',
    *,
    base_dir: 'Optional[Union[str, Path]]' = None,
) -> "'SizeDistribution'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** SizeDistribution or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

### `SingleParticleOptics`

**Import:** `zju_scatt_interface.SingleParticleOptics`.

Single-particle optical arrays loaded from a ZJU-SCATT L1 file.

```text
SingleParticleOptics(
    sizes: 'list[float]',
    extinction_cross_section: 'Optional[list[float]]' = None,
    scattering_cross_section: 'Optional[list[float]]' = None,
    absorption_cross_section: 'Optional[list[float]]' = None,
    extinction_efficiency: 'Optional[list[float]]' = None,
    scattering_efficiency: 'Optional[list[float]]' = None,
    absorption_efficiency: 'Optional[list[float]]' = None,
    asymmetry_factor: 'Optional[list[float]]' = None,
    phase_matrix: 'Optional[Any]' = None,
    scattering_angles: 'Optional[list[float]]' = None,
    size_unit: 'str' = 'unknown',
    cross_section_unit: 'str' = 'unknown',
    metadata: 'dict[str, Any]' = <factory>,
    projected_area: 'Optional[list[float]]' = None,
    single_scattering_albedo: 'Optional[list[float]]' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SingleParticleOptics` instance.

### `BulkOptics`

**Import:** `zju_scatt_interface.BulkOptics`.

Size-distribution-integrated optical properties.

```text
BulkOptics(
    extinction_coefficient: 'Optional[float]',
    scattering_coefficient: 'Optional[float]',
    absorption_coefficient: 'Optional[float]',
    single_scattering_albedo: 'Optional[float]',
    asymmetry_factor: 'Optional[float]',
    phase_matrix: 'Optional[Any]' = None,
    number_concentration: 'float' = 0.0,
    size_count: 'int' = 0,
    metadata: 'dict[str, Any]' = <factory>,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BulkOptics` instance.

#### `BulkOptics.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, Any]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

#### `BulkOptics.write_json`

Save this object's JSON representation.

```text
write_json(self, path: 'Union[str, Path]', *, indent: 'Optional[int]' = 2) -> 'Path'
```

**Inputs:** path: destination; indent: formatting control.

**Returns:** Path; writes a file, without recalculating optics.

### `PopulationResult`

**Import:** `zju_scatt_interface.PopulationResult`.

```text
PopulationResult(
    particle_type: 'str',
    wavelength_um: 'float',
    bulk: 'BulkOptics',
    qa: 'BulkQualityReport',
    members: 'tuple[EnsembleMemberResult, ...]',
    ensemble: 'Mapping[str, object]',
    uncertainty: 'Mapping[str, object]' = <factory>,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `PopulationResult` instance.

#### `PopulationResult.save`

Save a population and its diagnostic bundle.

```text
save(
    self,
    directory,
    *,
    component_name='bulk_optics',
    source_manifest=None,
    size_distribution=None,
    netcdf_path='bulk_optics.nc',
    title=None,
    include_members=False,
    l2_lognormal=False,
)
```

**Inputs:** directory; optional PSD, component/source metadata, NetCDF filename/title, include_members, and opt-in normalized dust L2 export.

**Returns:** Output/summary mapping; writes validated NetCDF, CSV, JSON and supplied PSD. L2 mode has additional scientific requirements.

#### `PopulationResult.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `BulkDataset`

**Import:** `zju_scatt_interface.BulkDataset`.

```text
BulkDataset(
    name: 'str',
    wavelengths_um: 'tuple[float, ...]',
    components: 'Mapping[str, tuple[PopulationResult, ...]]',
    mixture: 'tuple[BulkOptics, ...] | None' = None,
    dependency_plan: 'object | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BulkDataset` instance.

#### `BulkDataset.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `BulkGrid`

**Import:** `zju_scatt_interface.BulkGrid`.

Row-major calculation results over a ``SingleBulkScheme`` grid.

```text
BulkGrid(
    name: 'str',
    particle_type: 'str',
    dimensions: 'tuple[BulkDimension, ...]',
    calculations: 'tuple[PopulationResult, ...]',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BulkGrid` instance.

#### `BulkGrid.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `MultiBulkGrid`

**Import:** `zju_scatt_interface.MultiBulkGrid`.

Independent multidimensional grids for multiple particle types.

```text
MultiBulkGrid(name: 'str', components: 'Mapping[str, BulkGrid]') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `MultiBulkGrid` instance.

#### `MultiBulkGrid.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `DependencyPlan`

**Import:** `zju_scatt_interface.DependencyPlan`.

Complete source/cache state for one validated bulk scheme.

```text
DependencyPlan(
    schema_version: 'str',
    scheme_name: 'str',
    scheme_cache_key: 'str',
    offline: 'bool',
    workspace: 'WorkspaceLayout',
    manifest_path: 'Path',
    queries: 'Tuple[DependencyQuery, ...]',
    sources: 'Tuple[SourceEntry, ...]',
    issues: 'Tuple[DependencyIssue, ...]',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `DependencyPlan` instance.

#### `DependencyPlan.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

#### `DependencyPlan.write`

Save the dependency manifest to its workspace location.

```text
write(self) -> 'Path'
```

**Inputs:** The existing plan and its workspace.

**Returns:** Path of the written manifest.

### `OutputOptions`

**Import:** `zju_scatt_interface.OutputOptions`.

Storage controls shared by the NetCDF4 and HDF5 writers.

```text
OutputOptions(
    compression: 'bool' = True,
    compression_level: 'int' = 4,
    shuffle: 'bool' = True,
    chunk_wavelength: 'Optional[int]' = None,
    atomic: 'bool' = True,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OutputOptions` instance.

### `ApiClient`

**Import:** `zju_scatt_interface.access.ApiClient`.

Small retrying client for the website API and public OSS bucket.

```text
ApiClient(
    timeout: 'float' = 30.0,
    retries: 'int' = 3,
    insecure: 'bool' = False,
    show_tls_warning: 'bool' = True,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `ApiClient` instance.

#### `ApiClient.get_bytes`

Read an HTTP resource.

```text
get_bytes(self, url: 'str') -> 'bytes'
```

**Inputs:** url: service/object URL.

**Returns:** bytes; performs network I/O.

#### `ApiClient.get_json`

Read a JSON HTTP response.

```text
get_json(self, url: 'str') -> 'dict'
```

**Inputs:** url.

**Returns:** dict; performs network I/O.

#### `ApiClient.post_json`

Submit a JSON service request.

```text
post_json(self, url: 'str', payload: 'dict', headers: 'Optional[dict[str, str]]' = None) -> 'dict'
```

**Inputs:** url, payload and optional headers.

**Returns:** Response dict; performs a network mutation according to the endpoint.

#### `ApiClient.list_page`

List one object-store page.

```text
list_page(self, prefix: 'str', *, delimiter: 'Optional[str]' = None, marker: 'str' = '') -> 'ListPage'
```

**Inputs:** prefix, optional delimiter and continuation marker.

**Returns:** ListPage; performs a network listing.

#### `ApiClient.iter_objects`

Iterate objects across listing pages.

```text
iter_objects(
    self,
    prefix: 'str',
    *,
    on_page: 'Optional[Callable[[int, int], None]]' = None,
) -> 'Iterator[RemoteObject]'
```

**Inputs:** prefix and optional on_page callback.

**Returns:** Iterator of RemoteObject; consumes network pages lazily.

#### `ApiClient.list_directory`

List immediate remote directories/objects.

```text
list_directory(self, prefix: 'str') -> 'tuple[list[RemoteDirectory], list[RemoteObject], int]'
```

**Inputs:** prefix.

**Returns:** (list[RemoteDirectory], list[RemoteObject], page count).

#### `ApiClient.stat_object`

Inspect remote object metadata.

```text
stat_object(self, key: 'str') -> 'Optional[RemoteObject]'
```

**Inputs:** key: remote object key.

**Returns:** RemoteObject or None when absent; performs a metadata request.

#### `ApiClient.validate_session`

Check remote session validity.

```text
validate_session(self, token: 'str') -> 'bool'
```

**Inputs:** token: session secret.

**Returns:** bool; network validation, without saving a new session.

#### `ApiClient.register`

Submit a registration payload.

```text
register(self, payload: 'dict') -> 'str'
```

**Inputs:** payload: researcher identity/consent fields.

**Returns:** Session token string (secret); network registration. Prefer register_direct for local persistence.

#### `ApiClient.track_event`

Record an authorized usage event.

```text
track_event(self, token: 'str', key: 'str', event_type: 'str') -> 'None'
```

**Inputs:** token, object key and event_type.

**Returns:** None; performs a tracking request.

### `RemoteObject`

**Import:** `zju_scatt_interface.access.RemoteObject`.

Metadata returned by the OSS listing API.

```text
RemoteObject(key: 'str', size: 'int' = 0, last_modified: 'str' = '', etag: 'str' = '') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `RemoteObject` instance.

### `RemoteDirectory`

**Import:** `zju_scatt_interface.access.RemoteDirectory`.

A virtual directory represented by an OSS common prefix.

```text
RemoteDirectory(key: 'str') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `RemoteDirectory` instance.

### `RetrievalResult`

**Import:** `zju_scatt_interface.access.RetrievalResult`.

Result returned by the Python API retrieval helpers.

```text
RetrievalResult(
    objects: 'list[RemoteObject]',
    stats: 'ScanStats',
    wavelength_processing: 'WavelengthProcessing',
    target_processings: 'list[NumericSelectionProcessing]' = <factory>,
    manifest_path: 'Optional[Path]' = None,
    operation_log_path: 'Optional[Path]' = None,
    download_results: 'list[DownloadResult]' = <factory>,
    interpolated_products: 'list[Any]' = <factory>,
    status_code: 'int' = 0,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `RetrievalResult` instance.

#### `RetrievalResult.write_manifest`

Write selected source objects to a catalog manifest.

```text
write_manifest(self, path: 'Union[str, Path]', format_name: 'Optional[str]' = None) -> 'Path'
```

**Inputs:** path and optional format_name.

**Returns:** Path of the manifest.

#### `RetrievalResult.raise_for_status`

Require selected retrieval completion conditions.

```text
raise_for_status(self, *, download=False, require_matches=False, require_products=False)
```

**Inputs:** download, require_matches and require_products choose necessary checks.

**Returns:** The same RetrievalResult on success; ScattError if status/download/product requirements fail.

#### `RetrievalResult.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self)
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

#### `RetrievalResult.write_report`

Save a standard retrieval result report.

```text
write_report(self, path)
```

**Inputs:** path: JSON destination.

**Returns:** Path of the report.

### `DownloadResult`

**Import:** `zju_scatt_interface.access.DownloadResult`.

```text
DownloadResult(obj: 'RemoteObject', target: 'Path', status: 'str', message: 'str' = '') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `DownloadResult` instance.

### `ScanStats`

**Import:** `zju_scatt_interface.access.ScanStats`.

```text
ScanStats(pages: 'int' = 0, scanned: 'int' = 0, matched: 'int' = 0, bytes: 'int' = 0) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `ScanStats` instance.

### `WavelengthProcessing`

**Import:** `zju_scatt_interface.access.WavelengthProcessing`.

```text
WavelengthProcessing(
    target_um: 'Optional[float]' = None,
    target_wavelengths_um: 'tuple[float, ...]' = (),
    selected_wavelengths_um: 'tuple[float, ...]' = (),
    target_refractive_points: 'tuple[tuple[float, float], ...]' = (),
    selected_refractive_points: 'tuple[tuple[float, float], ...]' = (),
    selection_mode: 'str' = 'interp',
    interpolation_required: 'bool' = False,
    interpolation_applied: 'bool' = False,
    interpolation_basis: 'str' = 'none',
    message: 'str' = 'No target wavelength interpolation requested.',
    refractive_index_resolutions: 'tuple[dict, ...]' = (),
    target_temperatures_k: 'tuple[float, ...]' = (),
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `WavelengthProcessing` instance.

### `RetrievalRunResult`

**Import:** `zju_scatt_interface.access.RetrievalRunResult`.

```text
RetrievalRunResult(
    output_dir: 'Path',
    report_path: 'Path',
    results: 'dict' = <factory>,
    errors: 'dict' = <factory>,
    requests: 'dict' = <factory>,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `RetrievalRunResult` instance.

#### `RetrievalRunResult.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self)
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `RetrievalRunError`

**Import:** `zju_scatt_interface.access.RetrievalRunError`.

An incomplete batch; successful results and the report remain accessible.

### `EnsembleMemberResult`

**Import:** `zju_scatt_interface.bulk.EnsembleMemberResult`.

```text
EnsembleMemberResult(
    parameters: 'dict[str, float | str]',
    weight: 'float',
    bulk: 'BulkOptics',
    remap: 'RemapReport',
    qa: 'BulkQualityReport',
    convergence: 'BulkConvergenceReport',
    interpolation_provenance: 'Mapping[str, object]',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `EnsembleMemberResult` instance.

#### `EnsembleMemberResult.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `WeightedShapeEnsemble`

**Import:** `zju_scatt_interface.bulk.WeightedShapeEnsemble`.

Validated joint members whose weights sum to one.

```text
WeightedShapeEnsemble(members: 'Sequence[WeightedShapeMember | Mapping[str, object]]')
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `WeightedShapeEnsemble` instance.

#### `WeightedShapeEnsemble.from_shapes`

Preserve joint shape states in a normalized weighted ensemble.

```text
from_shapes(shapes, weights=None)
```

**Inputs:** shapes: mapping sequence; weights: matching explicit fractions or None for equal weights.

**Returns:** WeightedShapeEnsemble; incompatible lengths/weights raise.

#### `WeightedShapeEnsemble.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `WeightedShapeMember`

**Import:** `zju_scatt_interface.bulk.WeightedShapeMember`.

One correlated parameter/shape state and its population weight.

```text
WeightedShapeMember(
    parameters: 'Mapping[str, float | str] | None' = None,
    weight: 'float' = 1.0,
    **coordinates: 'float | str',
)
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `WeightedShapeMember` instance.

#### `WeightedShapeMember.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `WeightedValues`

**Import:** `zju_scatt_interface.bulk.WeightedValues`.

Independent parameter values with validated, normalized weights.

```text
WeightedValues(values: 'Sequence[float | str]', weights: 'Sequence[float]')
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `WeightedValues` instance.

#### `WeightedValues.from_value`

Construct/normalize this type from a supported representation.

```text
from_value(value: 'object') -> "'WeightedValues'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** WeightedValues or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `WeightedValues.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `BulkTableConfig`

**Import:** `zju_scatt_interface.bulk.BulkTableConfig`.

Short workflow configuration; unspecified species settings use literature_v1.

```text
BulkTableConfig(
    wavelengths: 'object',
    species: 'object' = 'all',
    preset: 'str' = 'literature_v1',
    overrides: 'Mapping' = <factory>,
    number_concentration_cm3: 'float' = 1.0,
    include_phase_matrix: 'bool' = False,
    coverage_policy: 'str' = 'error',
    workspace: 'object' = 'zju_scatt_data',
    offline: 'bool' = False,
    source_paths: 'Mapping' = <factory>,
    catalog: 'object' = None,
    reuse_dirs: 'object' = (),
    output_dir: 'object' = None,
    formats: 'object' = ('nc', 'csv'),
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BulkTableConfig` instance.

#### `BulkTableConfig.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(value, *, base_dir=None)
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** BulkTableConfig or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

### `BulkTableResult`

**Import:** `zju_scatt_interface.bulk.BulkTableResult`.

```text
BulkTableResult(scheme: 'BulkDataset', report: 'dict') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BulkTableResult` instance.

#### `BulkTableResult.save`

Save a table result with its assumptions report.

```text
save(self, directory, formats=('nc', 'csv'))
```

**Inputs:** directory and selected formats ('nc', 'csv').

**Returns:** Output-path mapping; writes selected data and report artifacts.

### `BulkDimension`

**Import:** `zju_scatt_interface.bulk.BulkDimension`.

One retained output axis and its explicit coordinate values.

```text
BulkDimension(
    name: 'str',
    coordinates: 'tuple[float | str, ...]',
    unit: 'str' = '1',
    description: 'str' = '',
    parameter: 'str | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BulkDimension` instance.

#### `BulkDimension.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(value: 'Mapping[str, Any]') -> "'BulkDimension'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** BulkDimension or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `BulkDimension.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `SingleBulkScheme`

**Import:** `zju_scatt_interface.bulk.SingleBulkScheme`.

A retained multidimensional bulk-optics grid for one particle type.

```text
SingleBulkScheme(name: 'str', component: 'ParticleComponent', dimensions: 'tuple[BulkDimension, ...]') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SingleBulkScheme` instance.

#### `SingleBulkScheme.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(
    value: 'Mapping[str, Any]',
    *,
    index: 'int' = 0,
    base_dir: 'str | Path | None' = None,
) -> "'SingleBulkScheme'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** SingleBulkScheme or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `SingleBulkScheme.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

#### `SingleBulkScheme.build`

Calculate every coordinate state of one retained grid.

```text
build(self, source_paths: 'object' = None, **kwargs: 'object') -> "'BulkGrid'"
```

**Inputs:** scheme: SingleBulkScheme; source_paths: explicit local sources. Remaining keywords select phase, truncation, convergence and QA policies.

**Returns:** BulkGrid with retained dimensions and population calculations; no cross-state averaging.

### `MultiBulkScheme`

**Import:** `zju_scatt_interface.bulk.MultiBulkScheme`.

Multiple independent particle-type bulk grids.

```text
MultiBulkScheme(name: 'str', particles: 'tuple[SingleBulkScheme, ...]') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `MultiBulkScheme` instance.

#### `MultiBulkScheme.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(value: 'Mapping[str, Any]', *, base_dir: 'str | Path | None' = None) -> "'MultiBulkScheme'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** MultiBulkScheme or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `MultiBulkScheme.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

#### `MultiBulkScheme.build`

Calculate independent retained grids for several populations.

```text
build(self, source_paths: 'Mapping[str, object] | object' = None, **kwargs: 'object') -> "'MultiBulkGrid'"
```

**Inputs:** scheme: MultiBulkScheme; source_paths: local sources by name/type or supported shared source input. kwargs follow build_grid.

**Returns:** MultiBulkGrid; populations are not implicitly mixed.

### `ParticleComponent`

**Import:** `zju_scatt_interface.config.ParticleComponent`.

One independently named particle population in a bulk scheme.

```text
ParticleComponent(
    name: 'str',
    particle_type: 'str',
    size_distribution: 'SizeDistribution',
    refractive_index: 'Mapping[str, Any]',
    shape_parameters: 'Mapping[str, Any]' = <factory>,
    shape_ensemble: 'tuple[Mapping[str, Any], ...]' = (),
    source: 'Optional[str]' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `ParticleComponent` instance.

#### `ParticleComponent.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(
    value: 'Mapping[str, Any]',
    index: 'int' = 0,
    *,
    base_dir: 'Union[str, Path, None]' = None,
) -> "'ParticleComponent'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** ParticleComponent or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `ParticleComponent.from_dict`

Construct/normalize this type from a supported representation.

```text
from_dict(value: 'Mapping[str, Any]', *, base_dir: 'Union[str, Path, None]' = None) -> "'ParticleComponent'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** ParticleComponent or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `ParticleComponent.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `IceComponent`

**Import:** `zju_scatt_interface.config.IceComponent`.

Typed super-spheroid ice component.

```text
IceComponent(
    name: 'str',
    *,
    temperature_k: 'float',
    size_distribution: 'Optional[SizeDistribution]' = None,
    size: 'object' = None,
    dndr: 'object' = None,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    roundness: 'object' = None,
    aspect_ratio: 'object' = None,
    shape_ensemble: 'Sequence[Mapping[str, Any]]' = (),
    source: 'Optional[Union[str, Path]]' = None,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `IceComponent` instance.

### `SeaSaltComponent`

**Import:** `zju_scatt_interface.config.SeaSaltComponent`.

Typed coated-super-spheroid sea-salt component.

```text
SeaSaltComponent(
    name: 'str',
    *,
    relative_humidity: 'object',
    humidity_branch: 'object' = None,
    size_distribution: 'Optional[SizeDistribution]' = None,
    size: 'object' = None,
    dndr: 'object' = None,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    shape_ensemble: 'Sequence[Mapping[str, Any]]' = (),
    source: 'Optional[Union[str, Path]]' = None,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SeaSaltComponent` instance.

### `DustComponent`

**Import:** `zju_scatt_interface.config.DustComponent`.

Readable alias for a dust population using the super-spheroid database.

```text
DustComponent(
    name: 'str',
    *,
    refractive_index: 'object',
    roundness: 'object' = None,
    aspect_ratio: 'object' = None,
    size_distribution: 'Optional[SizeDistribution]' = None,
    size: 'object' = None,
    dndr: 'object' = None,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    shape_ensemble: 'Sequence[Mapping[str, Any]]' = (),
    source: 'Optional[Union[str, Path]]' = None,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `DustComponent` instance.

### `SuperSpheroidComponent`

**Import:** `zju_scatt_interface.config.SuperSpheroidComponent`.

Typed native mr/mi-grid super-spheroid component.

```text
SuperSpheroidComponent(
    name: 'str',
    *,
    refractive_index: 'object',
    roundness: 'object' = None,
    aspect_ratio: 'object' = None,
    size_distribution: 'Optional[SizeDistribution]' = None,
    size: 'object' = None,
    dndr: 'object' = None,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    shape_ensemble: 'Sequence[Mapping[str, Any]]' = (),
    source: 'Optional[Union[str, Path]]' = None,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SuperSpheroidComponent` instance.

### `BlackCarbonComponent`

**Import:** `zju_scatt_interface.config.BlackCarbonComponent`.

Typed encapsulated fractal-aggregate black-carbon component.

```text
BlackCarbonComponent(
    name: 'str',
    *,
    df: 'object',
    vf: 'object',
    refractive_index: 'object',
    database_type: 'str' = 'refractive_index_grid',
    ri_scheme: 'Optional[str]' = None,
    size_distribution: 'Optional[SizeDistribution]' = None,
    size: 'object' = None,
    dndr: 'object' = None,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    shape_ensemble: 'Sequence[Mapping[str, Any]]' = (),
    source: 'Optional[Union[str, Path]]' = None,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BlackCarbonComponent` instance.

### `HygroscopicSphereComponent`

**Import:** `zju_scatt_interface.config.HygroscopicSphereComponent`.

Typed sulfate, nitrate, or organic-carbon sphere component.

```text
HygroscopicSphereComponent(
    name: 'str',
    *,
    material: 'str',
    relative_humidity: 'object',
    size_distribution: 'Optional[SizeDistribution]' = None,
    size: 'object' = None,
    dndr: 'object' = None,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    shape_ensemble: 'Sequence[Mapping[str, Any]]' = (),
    source: 'Optional[Union[str, Path]]' = None,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `HygroscopicSphereComponent` instance.

### `WaterCloudComponent`

**Import:** `zju_scatt_interface.config.WaterCloudComponent`.

Typed spherical liquid-water cloud component.

```text
WaterCloudComponent(
    name: 'str',
    *,
    size_distribution: 'Optional[SizeDistribution]' = None,
    size: 'object' = None,
    dndr: 'object' = None,
    size_unit: 'str' = 'um',
    size_definition: 'str' = 'volume_equivalent_sphere_radius',
    source: 'Optional[Union[str, Path]]' = None,
) -> 'None'
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `WaterCloudComponent` instance.

### `SulfateComponent`

**Import:** `zju_scatt_interface.config.SulfateComponent`.

Typed sulfate sphere component.

```text
SulfateComponent(name: 'str', *, relative_humidity: 'object', **kwargs: 'object')
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SulfateComponent` instance.

### `NitrateComponent`

**Import:** `zju_scatt_interface.config.NitrateComponent`.

Typed nitrate sphere component.

```text
NitrateComponent(name: 'str', *, relative_humidity: 'object', **kwargs: 'object')
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `NitrateComponent` instance.

### `OrganicCarbonComponent`

**Import:** `zju_scatt_interface.config.OrganicCarbonComponent`.

Typed organic-carbon sphere component.

```text
OrganicCarbonComponent(name: 'str', *, relative_humidity: 'object', **kwargs: 'object')
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OrganicCarbonComponent` instance.

### `DatabaseRefractiveIndex`

**Import:** `zju_scatt_interface.config.DatabaseRefractiveIndex`.

Use database wavelength optics, optionally at an ice temperature.

```text
DatabaseRefractiveIndex(temperature_k: 'Optional[float]' = None) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `DatabaseRefractiveIndex` instance.

#### `DatabaseRefractiveIndex.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `FixedRefractiveIndex`

**Import:** `zju_scatt_interface.config.FixedRefractiveIndex`.

Advanced native-grid refractive-index override.

```text
FixedRefractiveIndex(real: 'float', imaginary: 'float') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `FixedRefractiveIndex` instance.

#### `FixedRefractiveIndex.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `TableRefractiveIndex`

**Import:** `zju_scatt_interface.config.TableRefractiveIndex`.

External wavelength-to-index table for a native mr/mi grid database.

```text
TableRefractiveIndex(file: 'Union[str, Path]') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `TableRefractiveIndex` instance.

#### `TableRefractiveIndex.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `BlackCarbonRefractiveIndex`

**Import:** `zju_scatt_interface.config.BlackCarbonRefractiveIndex`.

Two-material native refractive indices for encapsulated black carbon.

```text
BlackCarbonRefractiveIndex(
    black_carbon_real: 'float',
    black_carbon_imaginary: 'float',
    hygroscopic_real: 'float',
    hygroscopic_imaginary: 'float',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BlackCarbonRefractiveIndex` instance.

#### `BlackCarbonRefractiveIndex.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `BlackCarbonRefractiveIndexTables`

**Import:** `zju_scatt_interface.config.BlackCarbonRefractiveIndexTables`.

External material tables used by the black-carbon wavelength wrapper.

```text
BlackCarbonRefractiveIndexTables(
    black_carbon_file: 'Union[str, Path]',
    hygroscopic_file: 'Union[str, Path]',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `BlackCarbonRefractiveIndexTables` instance.

#### `BlackCarbonRefractiveIndexTables.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `SchemeOutput`

**Import:** `zju_scatt_interface.config.SchemeOutput`.

Declarative output path and storage controls.

```text
SchemeOutput(
    path: 'str' = 'bulk_optical_scheme.nc',
    format: 'str' = 'netcdf4',
    compression: 'bool' = True,
    compression_level: 'int' = 4,
    shuffle: 'bool' = True,
    chunk_wavelength: 'Optional[int]' = None,
    atomic: 'bool' = True,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SchemeOutput` instance.

#### `SchemeOutput.from_value`

Construct/normalize this type from a supported representation.

```text
from_value(value: 'object') -> "'SchemeOutput'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** SchemeOutput or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

#### `SchemeOutput.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `ParticleProfile`

**Import:** `zju_scatt_interface.config.ParticleProfile`.

Complete user-facing contract for one database particle family.

```text
ParticleProfile(
    particle_type: 'str',
    display_name: 'str',
    aliases: 'Tuple[str, ...]',
    database_directory: 'str',
    data_structure: 'DataStructure',
    parameters: 'Tuple[ParameterSpec, ...]',
    native_size_variables: 'Tuple[str, ...]',
    supported_size_definitions: 'Tuple[str, ...]',
    default_size_definition: 'str',
    source_schema: 'SourceSchema',
    native_lookup_coordinates: 'Tuple[str, ...]' = (),
    default_wrapper_input_mode: 'str' = 'native',
    forbidden_parameters: 'Tuple[str, ...]' = (),
    notes: 'Tuple[str, ...]' = (),
    refractive_index_parameters: 'Tuple[str, ...]' = (),
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `ParticleProfile` instance.

#### `ParticleProfile.parameter`

Look up one profile coordinate specification.

```text
parameter(self, name: 'str') -> 'ParameterSpec'
```

**Inputs:** name: canonical parameter or supported alias.

**Returns:** ParameterSpec with role, unit, ranges and source representation; unknown names raise KeyError.

#### `ParticleProfile.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'Dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `DataStructure`

**Import:** `zju_scatt_interface.config.DataStructure`.

Enum values: `grid_based`, `wavelength_based`; describes native database organization.

### `ExtensionError`

**Import:** `zju_scatt_interface.extensions.ExtensionError`.

An extension has an invalid contract or conflicts with another extension.

### `ParticleDefinition`

**Import:** `zju_scatt_interface.extensions.ParticleDefinition`.

Version-1 particle contract; callbacks use the existing optical/PSD units.

```text
ParticleDefinition(
    profile: 'object',
    adapter_factory: 'Callable',
    axes: 'tuple[str, ...]',
    planner: 'Callable',
    calculation_inputs: 'Callable',
    defaults: 'Callable | None' = None,
    interpolation_policy: 'Callable | None' = None,
    downloaded_interpolator: 'Callable | None' = None,
    ensemble_axes: 'tuple[str, ...]' = (),
    table_settings: 'Callable | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `ParticleDefinition` instance.

### `PSDFactory`

**Import:** `zju_scatt_interface.extensions.PSDFactory`.

create(config, context) validates its options and returns SizeDistribution.

```text
PSDFactory(create: Callable) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `PSDFactory` instance.

### `PSDContext`

**Import:** `zju_scatt_interface.extensions.PSDContext`.

```text
PSDContext(
    lower_um: float,
    upper_um: float,
    concentration_cm3: float = 1.0,
    reference: bool = False,
    conditional_reference: bool = False,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `PSDContext` instance.

### `Exporter`

**Import:** `zju_scatt_interface.extensions.Exporter`.

write(data, destination, **options), and optional validate(path, **options).

```text
Exporter(write: 'Callable', validate: 'Callable | None' = None) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `Exporter` instance.

### `Command`

**Import:** `zju_scatt_interface.extensions.Command`.

configure(parser), run(args, client) -> exit code; validate(args) optional.

```text
Command(
    name: 'str',
    help: 'str',
    configure: 'Callable',
    run: 'Callable',
    validate: 'Callable | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `Command` instance.

### `NativeModel`

**Import:** `zju_scatt_interface.extensions.NativeModel`.

Version-1 native template operations; unsupported capabilities stay explicit.

```text
NativeModel(
    validate: 'Callable',
    read: 'Callable | None' = None,
    template: 'Callable | None' = None,
    bulk_fields: 'Callable | None' = None,
    phase: 'Callable | None' = None,
    attribute: 'Callable | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `NativeModel` instance.

### `OutputValidationReport`

**Import:** `zju_scatt_interface.io.OutputValidationReport`.

Result of validating a written canonical product.

```text
OutputValidationReport(
    path: 'Path',
    format: 'str',
    passed: 'bool',
    components: 'tuple[str, ...]',
    errors: 'tuple[str, ...]' = (),
    warnings: 'tuple[str, ...]' = (),
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OutputValidationReport` instance.

#### `OutputValidationReport.require_valid`

Require every recorded file-quality check to pass.

```text
require_valid(self) -> "'OutputValidationReport'"
```

**Inputs:** Existing validation report instance.

**Returns:** The same report on success; ValueError on invalid output.

#### `OutputValidationReport.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `OpticalTableColumn`

**Import:** `zju_scatt_interface.io.OpticalTableColumn`.

One output column selected from a canonical optical record.

```text
OpticalTableColumn(
    field: 'str',
    name: 'Optional[str]' = None,
    unit: 'str' = '',
    format: 'Optional[str]' = None,
    scale: 'float' = 1.0,
    offset: 'float' = 0.0,
    transform: 'Optional[ValueTransform]' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OpticalTableColumn` instance.

#### `OpticalTableColumn.from_value`

Construct/normalize this type from a supported representation.

```text
from_value(value: 'object') -> "'OpticalTableColumn'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** OpticalTableColumn or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

### `OpticalTableFormat`

**Import:** `zju_scatt_interface.io.OpticalTableFormat`.

Complete, versionable specification for a rendered optical table.

```text
OpticalTableFormat(
    name: 'str',
    columns: 'tuple[OpticalTableColumn, ...]',
    delimiter: 'str' = ' ',
    header_lines: 'tuple[str, ...]' = (),
    include_column_header: 'bool' = True,
    include_unit_header: 'bool' = False,
    comment_prefix: 'str' = '# ',
    row_template: 'Optional[str]' = None,
    missing_value: 'str' = 'nan',
    strict_fields: 'bool' = True,
    line_ending: 'str' = '\n',
    layout: 'str' = 'combined',
    filename_template: 'str' = '{stem}_{component}{suffix}',
    record_transform: 'Optional[RecordTransform]' = None,
    record_filter: 'Optional[RecordFilter]' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OpticalTableFormat` instance.

#### `OpticalTableFormat.from_mapping`

Construct/normalize this type from a supported representation.

```text
from_mapping(value: 'Mapping[str, object]') -> "'OpticalTableFormat'"
```

**Inputs:** value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.

**Returns:** OpticalTableFormat or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.

### `OpticalNode`

**Import:** `zju_scatt_interface.optics.OpticalNode`.

One source product at a known set of canonical scientific coordinates.

```text
OpticalNode(coordinates: 'Mapping[str, float | str]', optics: 'SingleParticleOptics', source: 'str' = '') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OpticalNode` instance.

### `OpticalSourceRequest`

**Import:** `zju_scatt_interface.optics.OpticalSourceRequest`.

Description of an L1 source file that can be loaded as an optical node.

```text
OpticalSourceRequest(
    path: 'str | Path',
    coordinates: 'Mapping[str, float | str]',
    coordinate_indices: 'Mapping[str, int]' = <factory>,
    wavelength_um: 'float | None' = None,
    include_phase_matrix: 'bool' = False,
    size_dataset: 'str | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OpticalSourceRequest` instance.

### `InterpolatedOpticalProduct`

**Import:** `zju_scatt_interface.optics.InterpolatedOpticalProduct`.

```text
InterpolatedOpticalProduct(
    particle_type: 'str',
    coordinates: 'dict[str, float | str]',
    optics: 'SingleParticleOptics',
    provenance: 'InterpolationProvenance',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `InterpolatedOpticalProduct` instance.

### `InterpolationProvenance`

**Import:** `zju_scatt_interface.optics.InterpolationProvenance`.

```text
InterpolationProvenance(
    method: 'str',
    particle_type: 'str',
    target_coordinates: 'dict[str, float | str]',
    axis_transforms: 'dict[str, str]',
    optical_transforms: 'dict[str, str]',
    neighbors: 'list[InterpolationNeighbor]',
    size_grid_um: 'list[float]',
    angle_grid_degrees: 'list[float]',
    no_extrapolation: 'bool' = True,
    phase_normalization: 'str' = 'preserve',
    constraint_corrections: 'list[str]' = <factory>,
    warnings: 'list[str]' = <factory>,
    adapter: 'dict[str, Any]' = <factory>,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `InterpolationProvenance` instance.

#### `InterpolationProvenance.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, Any]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `InterpolationError`

**Import:** `zju_scatt_interface.optics.InterpolationError`.

Raised when a requested product cannot be interpolated safely.

### `ComplexRefractiveIndex`

**Import:** `zju_scatt_interface.optics.ComplexRefractiveIndex`.

```text
ComplexRefractiveIndex(real: 'float', imaginary: 'float') -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `ComplexRefractiveIndex` instance.

### `RefractiveIndexTable`

**Import:** `zju_scatt_interface.optics.RefractiveIndexTable`.

A validated wavelength-indexed external refractive-index table.

```text
RefractiveIndexTable(
    wavelength_um: 'Tuple[float, ...]',
    real: 'Tuple[float, ...]',
    imaginary: 'Tuple[float, ...]',
    source: 'str' = 'in_memory',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `RefractiveIndexTable` instance.

#### `RefractiveIndexTable.interpolate`

Interpolate a material index at a physical wavelength.

```text
interpolate(self, wavelength_um: 'object', *, extrapolate: 'bool' = False) -> 'ComplexRefractiveIndex'
```

**Inputs:** wavelength_um; extrapolate is explicit and defaults False. Research workflows should remain within verified coverage.

**Returns:** ComplexRefractiveIndex containing real/imaginary values.

#### `RefractiveIndexTable.from_csv`

Read a material's wavelength-dependent complex indices.

```text
from_csv(
    path: 'Union[str, Path]',
    *,
    wavelength_unit: 'Optional[str]' = None,
    wavelength_column: 'Optional[str]' = None,
    real_column: 'Optional[str]' = None,
    imaginary_column: 'Optional[str]' = None,
) -> "'RefractiveIndexTable'"
```

**Inputs:** path; optional wavelength unit and real/imaginary/wavelength column names.

**Returns:** RefractiveIndexTable; verifies supported CSV representation.

### `OpticalPlotStyle`

**Import:** `zju_scatt_interface.plotting.OpticalPlotStyle`.

Shared inspection style; layouts must contain four/six panels respectively.

```text
OpticalPlotStyle(
    font_family: 'str' = 'DejaVu Sans',
    font_size: 'float' = 10,
    line_width: 'float' = 1.5,
    scalar_layout: 'tuple' = (2, 2),
    phase_layout: 'tuple' = (2, 3),
    scalar_figsize: 'tuple' = (10, 7),
    phase_figsize: 'tuple' = (12, 6.6),
    colors: 'tuple' = ('#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#000000'),
    line_styles: 'tuple' = ('-', '--', '-.', ':'),
    grid_alpha: 'float' = 0.2,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `OpticalPlotStyle` instance.

### `RemapReport`

**Import:** `zju_scatt_interface.psd.RemapReport`.

```text
RemapReport(
    source_number_concentration_cm3: 'float',
    output_number_concentration_cm3: 'float',
    outside_number_concentration_cm3: 'float',
    outside_fraction: 'float',
    truncation_policy: 'str',
    source_range_um: 'Tuple[float, float]',
    target_range_um: 'Tuple[float, float]',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `RemapReport` instance.

#### `RemapReport.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `WorkspaceLayout`

**Import:** `zju_scatt_interface.sources.WorkspaceLayout`.

Deterministic directories used by a scheme source build.

```text
WorkspaceLayout(
    root: 'Path',
    cache_dir: 'Path',
    work_dir: 'Path',
    manifest_dir: 'Path',
    output_file: 'Path',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `WorkspaceLayout` instance.

#### `WorkspaceLayout.create`

Create a dependency workspace layout.

```text
create(root: 'Union[str, Path]', output: 'Union[str, Path]') -> "'WorkspaceLayout'"
```

**Inputs:** root and scheme output path.

**Returns:** WorkspaceLayout; creates cache/work/manifest directories and resolves output location.

#### `WorkspaceLayout.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, str]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `SourceInspection`

**Import:** `zju_scatt_interface.sources.SourceInspection`.

```text
SourceInspection(
    path: 'Path',
    particle_type: 'str',
    dataset_name: 'str',
    data_version: 'str',
    valid: 'bool',
    errors: 'Tuple[str, ...]',
    variables: 'Mapping[str, VariableSummary]',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `SourceInspection` instance.

#### `SourceInspection.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'Dict[str, object]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `AdapterResolution`

**Import:** `zju_scatt_interface.sources.adapters.AdapterResolution`.

```text
AdapterResolution(
    particle_type: 'str',
    target_coordinates: 'dict[str, float | str]',
    sources: 'tuple[OpticalSourceRequest, ...]',
    provenance: 'AdapterProvenance',
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `AdapterResolution` instance.

#### `AdapterResolution.interpolate`

Load/align the resolution's selected source nodes and interpolate optics.

```text
interpolate(
    self,
    *,
    target_size_um: 'Sequence[float] | None' = None,
    source_size_grids_um: 'Mapping[str | Path, Sequence[float]] | None' = None,
    drop_invalid_size_points: 'bool' = False,
    target_angles_degrees: 'Sequence[float] | None' = None,
    phase_normalization: 'str' = 'preserve',
) -> 'InterpolatedOpticalProduct'
```

**Inputs:** Optional output size/angle grids, source size grids and explicit invalid-point/phase policies.

**Returns:** InterpolatedOpticalProduct with source provenance.

### `AdapterProvenance`

**Import:** `zju_scatt_interface.sources.adapters.AdapterProvenance`.

```text
AdapterProvenance(
    adapter: 'str',
    particle_type: 'str',
    public_wavelength_um: 'float',
    target_native_coordinates: 'dict[str, float | str]',
    size_definition: 'str',
    source_candidate_count: 'int',
    selected_node_count: 'int',
    refractive_index_input_mode: 'str' = 'database',
    refractive_index_sources: 'dict[str, str]' = <factory>,
    coordinate_conversions: 'list[str]' = <factory>,
    defaults_applied: 'list[str]' = <factory>,
    database_type: 'str | None' = None,
    ri_scheme: 'str | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `AdapterProvenance` instance.

#### `AdapterProvenance.to_dict`

Serialize the object's recorded fields without recomputation.

```text
to_dict(self) -> 'dict[str, Any]'
```

**Inputs:** No scientific inputs beyond the existing instance.

**Returns:** Mapping containing the recorded fields and available nested diagnostics.

### `AdapterSourceNode`

**Import:** `zju_scatt_interface.sources.adapters.AdapterSourceNode`.

```text
AdapterSourceNode(
    path: 'Path',
    coordinates: 'Mapping[str, float | str]',
    coordinate_indices: 'Mapping[str, int]' = <factory>,
    wavelength_um: 'float | None' = None,
) -> None
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `AdapterSourceNode` instance.

#### `AdapterSourceNode.to_request`

Convert an adapter-selected node to a loading request.

```text
to_request(self, *, include_phase_matrix: 'bool', size_dataset: 'str') -> 'OpticalSourceRequest'
```

**Inputs:** include_phase_matrix and size_dataset explicitly control loading.

**Returns:** OpticalSourceRequest for the selected native source.

### `ParticleAdapter`

**Import:** `zju_scatt_interface.sources.adapters.ParticleAdapter`.

Base class for one scientifically explicit particle-family adapter.

```text
ParticleAdapter()
```

**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `ParticleAdapter` instance.

#### `ParticleAdapter.resolve`

Resolve local particle files to minimal native source nodes.

```text
resolve(
    self,
    source_paths: 'str | Path | Sequence[str | Path]',
    *,
    wavelength: 'object',
    wavelength_unit: 'str' = 'um',
    parameters: 'Mapping[str, object] | None' = None,
    refractive_index_tables: 'Mapping[str, str | Path | RefractiveIndexTable] | None' = None,
    size_definition: 'str | None' = None,
    include_phase_matrix: 'bool' = False,
) -> 'AdapterResolution'
```

**Inputs:** particle_type, local source_paths; kwargs include wavelength/unit, parameters, RI tables, size definition and phase loading requirements.

**Returns:** AdapterResolution with target coordinates, selected source nodes and provenance.

### `AdapterError`

**Import:** `zju_scatt_interface.sources.adapters.AdapterError`.

Public parameters cannot be resolved to native L1 nodes.

### `DatabaseBoundaryError`

**Import:** `zju_scatt_interface.sources.adapters.DatabaseBoundaryError`.

A valid request falls outside the selected database's support.

### `DatabaseBoundaryWarning`

**Import:** `zju_scatt_interface.sources.adapters.DatabaseBoundaryWarning`.

Optical results are NaN because database support is insufficient.
