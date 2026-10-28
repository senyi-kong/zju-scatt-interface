"""Build the release reference from real exports plus reviewed semantic notes.

Only writes docs/FUNCTION_REFERENCE.md. Never calls scientific/session functions.
Run from any directory with the project source available.
"""
from __future__ import annotations

import importlib
import inspect
import re
import sys
from collections import OrderedDict
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from source_checkout import load_source_package

load_source_package(ROOT)

# purpose; interpretation of inputs; actual return and relevant side effects.
NOTES = {
    "load_scheme": ("Load a portable bulk scheme.", "path: JSON or a trusted Python file defining bulk_scheme, BULK_SCHEME or config. Relative scientific paths are resolved beside that file.", "Scheme; malformed/unsupported input raises. Python input executes code."),
    "get_particle_profile": ("Describe one registered particle family (root alias: describe_particle).", "particle_type: canonical name or registered alias.", "ParticleProfile with parameters, roles, bounds, native coordinates and source requirements."),
    "plan": ("Inspect a scheme's source dependencies without optical downloads.", "scheme: Scheme, compatible mapping or scheme path. Options follow prepare_scheme_dependencies, except download=True is rejected. workspace and offline control catalog/cache inspection.", "DependencyPlan for built-in schemes. May inspect the network and write manifests; an incomplete plan records issues."),
    "retrieve": ("Run checked single/batch retrieval from a configuration.", "config: path, mapping, or supported retrieval config. Optional non-None keyword overrides replace download/output/manifest/overwrite/diagnostic settings; client supplies a transport.", "RetrievalRunResult with named results and single for a successful one-population run. Downloads/interpolates by configured defaults; failed runs raise RetrievalRunError carrying result."),
    "interpolate": ("Dispatch interpolation for homogeneous source objects.", "sources: nonempty sequence of OpticalNode or OpticalSourceRequest; target: coordinate mapping; particle_type: profile. Options follow the selected interpolation handler.", "InterpolatedOpticalProduct with optics and interpolation provenance for built-ins; unsupported/mixed input types raise."),
    "integrate": ("Integrate a loaded physical optical slice over a PSD.", "optics: SingleParticleOptics; distribution: SizeDistribution. Size-definition conversion requires justified geometry; truncation_policy controls uncovered bins.", "(BulkOptics, RemapReport). Does not select/download sources."),
    "combine": ("Combine extensive coefficients and re-derive intensive optical quantities.", "results: compatible BulkOptics sequence; weights: optional nonnegative population weights; metadata: explicit additional provenance.", "BulkOptics; SSA, asymmetry and phases are derived with physical coefficient weighting."),
    "compute_population": ("Calculate one particle population at one wavelength, including ensemble diagnostics.", "particle_type, local source_paths and size_distribution are required, together with wavelength. parameters supplies profile coordinates/RI; shape_ensemble preserves joint states. Phase, size, truncation, QA and convergence keywords control explicit scientific policies.", "PopulationResult: bulk optics, per-member remapping/QA/convergence/provenance and ensemble metadata. Invalid strict checks raise."),
    "build": ("Build the requested scheme/product type through a registered handler.", "scheme: ordinary scheme/path/mapping, SingleBulkScheme or MultiBulkScheme. Ordinary schemes accept plan=DependencyPlan; remaining options follow build_dataset. Grid schemes use source_paths and grid-build options instead of plan.", "BulkDataset for an ordinary scheme; BulkGrid or MultiBulkGrid for retained grids. Returns data; call write to save. Incomplete plans refresh in their workspace, inheriting offline policy."),
    "validate": ("Validate a supported scientific input or saved product.", "product: Scheme, BulkOptics, or canonical bulk file path for built-ins. Options are forwarded to that type's validator. Load a scheme path before using this operation on its configuration.", "Scheme -> dependency-query tuple; BulkOptics -> BulkQualityReport; file path -> OutputValidationReport. This is not one uniform report type."),
    "read": ("Read canonical NetCDF4/HDF5 output into an inspection mapping.", "path: canonical bulk file; format: optional explicit netcdf4/hdf5 selector, otherwise inferred.", "dict with attributes, datasets and named components; does not reconstruct calculation/result objects."),
    "write": ("Write a supported product in a canonical format.", "product: dataset, grid, population, table result, bare BulkOptics or supported homogeneous sequence. path selects destination; format overrides suffix inference. Bare optics require wavelength_um; bare-optics sequences require wavelengths_um. Options include canonical OutputOptions/provenance where supported.", "Destination Path for built-in writers; validates before atomic replacement by default. Existing destination can be replaced."),
    "plot": ("Plot a typed product or explicitly identified file kind.", "product: supported optics/bulk object or file. File paths require kind='single'/'bulk'; options follow plot_single_scattering or plot_bulk_optics.", "Inspection/output mapping from the selected built-in plotter, including generated files and selection information. Writes plot artifacts; no optical recalculation."),
    "register_direct": ("Register through the service and save the session locally.", "organization, country and explicit consent; optional researcher information, dataset needs, minimal mode and client. Supply the researcher's actual information.", "Session token string (secret); also writes local session configuration. Never include this return in chat or shared reports."),
    "load_session_token": ("Resolve an existing session token.", "explicit: optional token override; otherwise checks environment and local saved registration.", "Token string or None (secret). Does not establish remote validity."),
    "save_session_token": ("Persist a token and optional registration metadata.", "token: valid registered session secret; metadata: optional mapping for local storage.", "None; writes local session configuration. Do not place secrets in a scientific input."),
    "search_data": ("Return the remote objects selected by a retrieval query.", "parameters are forwarded to retrieve_sources, including client/transport options, sources or manifest, particle_types, wavelength/shape/RI selections and filters. download defaults to False; an explicitly supplied value is preserved. Normal registration is required by retrieve_sources. Optional manifest/log paths retain their normal effects.", "list[RemoteObject], taken from RetrievalResult.objects. This convenience wrapper does not return the complete retrieval report or enforce its completion status; use retrieve_sources when those checks are needed."),
    "estimate_data": ("Return scan and storage statistics for a retrieval query.", "parameters follow retrieve_sources, including sources or manifest, particle and scientific selectors, filters and client/transport options. download defaults to False; an explicitly supplied value is preserved. Normal registration is required by retrieve_sources. Optional manifest/log paths retain their normal effects.", "ScanStats, taken from RetrievalResult.stats. This is the query's statistics record, not a download or numerical-build result; use retrieve_sources for the complete result and status."),
    "retrieve_sources": ("Select native sources with optional downloads/interpolation.", "client/timeout/retries/insecure control transport. parameters uses the retrieval keyword contract: particle_types, sources/manifest, target_wavelengths, shapes, target_temperatures, refractive_index_parameters, download, output_dir, apply_interpolation and filters.", "RetrievalResult with selected objects, byte estimate, download records and derived products. Lower-level completion must be checked explicitly."),
    "load_retrieval_config": ("Load configured retrieval inputs.", "config: in-memory mapping, JSON path or trusted Python path defining retrieval.", "Normalized retrieval configuration mapping; Python files execute code."),
    "initialize_data_directory": ("Create/select the default retrieval storage directory.", "path: local directory path.", "Path; creates the directory and changes the current process's default retrieval destination."),
    "integrate_arrays": ("Integrate explicit optical arrays with a conservatively remapped PSD.", "distribution: typed PSD; database_size_um: source physical radius grid. Supply matching cross sections in m2 or supported efficiencies, optional asymmetry/phases, geometry policy and metadata.", "(BulkOptics, RemapReport). Caller is responsible for physically consistent source arrays and metadata."),
    "build_dataset": ("Build every named component of an ordinary bulk scheme.", "config: Scheme or supported scheme input. source_paths can override all component sources; dependency_plan is the specialist keyword. workspace/offline and scientific options control source preparation and repeated population calculations.", "BulkDataset with independent components and retained dependency information. This specialist API differs from root build(plan=...)."),
    "build_table": ("Build configured reference/override spectra and optional outputs.", "config: BulkTableConfig, mapping, JSON or trusted Python input defining bulk_table; progress: callback for progress messages.", "BulkTableResult with rows, scheme and assumptions report. Writes configured output_dir formats if supplied."),
    "load_table_config": ("Read a table workflow configuration.", "path: JSON or trusted Python file defining bulk_table; relative paths resolve beside the input file.", "BulkTableConfig; Python input executes code."),
    "resolve_bulk_settings": ("Inspect preset assumptions combined with particle overrides.", "particle_type: profile; overrides: explicit mapping; preset: reference preset name.", "Resolved settings mapping; performs no downloads or optical calculation."),
    "build_grid": ("Calculate every coordinate state of one retained grid.", "scheme: SingleBulkScheme; source_paths: explicit local sources. Remaining keywords select phase, truncation, convergence and QA policies.", "BulkGrid with retained dimensions and population calculations; no cross-state averaging."),
    "build_grids": ("Calculate independent retained grids for several populations.", "scheme: MultiBulkScheme; source_paths: local sources by name/type or supported shared source input. kwargs follow build_grid.", "MultiBulkGrid; populations are not implicitly mixed."),
    "load_grid_scheme": ("Load retained-grid definitions from a Python configuration.", "path: trusted Python file defining multi_bulk_scheme.", "MultiBulkScheme; loading executes the Python file."),
    "list_particle_profiles": ("List registered particle contracts.", "No arguments.", "Tuple of ParticleProfile values, including registered extensions."),
    "scheme_reference": ("Inspect the machine-readable domain/command contract.", "particle_type: optional profile filter.", "dict containing scheme fields, units, profile metadata and command templates; not a generic JSON Schema or availability check."),
    "write_scheme_reference": ("Save the machine-readable reference.", "path: JSON destination; particle_type: optional profile filter.", "Path; writes deterministic reference JSON."),
    "register_particle": ("Register a complete particle extension contract.", "definition: ParticleDefinition with profile, native axes and required callbacks.", "Registered ParticleDefinition; conflicting names/aliases or invalid callbacks raise ExtensionError."),
    "get_particle_definition": ("Look up a registered particle implementation contract.", "name: canonical particle name or alias.", "ParticleDefinition; unknown name raises ExtensionError."),
    "register_operation": ("Register a type-specific public operation handler.", "operation: supported operation name; product_type: dispatch class; handler: callable receiving product and operation options (plus path for write).", "Registered handler callable; rejects duplicate type bindings or unsupported operation names."),
    "register_plotter": ("Register an explicit plot kind.", "kind: unique name; handler: callable receiving product and plot options.", "Registered handler callable; rejects conflicts and noncallable handlers."),
    "create_psd": ("Create a PSD through a registered named factory.", "config: mapping containing type and factory-specific settings; context: PSDContext with physical support and concentration.", "SizeDistribution; rejects factories returning an incompatible type."),
    "register_psd": ("Add a named analytical/custom PSD factory.", "name, PSDFactory and optional aliases.", "Registered PSDFactory; does not create a PSD or perform a calculation."),
    "register_exporter": ("Add a named application exporter.", "name, Exporter(write, optional validate), and aliases.", "Registered Exporter contract; does not write files at registration time."),
    "export": ("Invoke a registered application writer.", "application: exporter name; data: supported product; destination: exporter-specific path/directory; options follow that writer.", "The selected exporter's result (built-ins return manifest mappings); creates application outputs."),
    "validate_export": ("Invoke a registered application validator.", "application: exporter name; path: written product; options follow the validator.", "Validator result mapping for supported built-ins; raises when no validator is registered."),
    "register_command": ("Register a CLI command before constructing the parser.", "command: Command with name/help, configure and run callbacks, plus optional validate.", "Registered Command; built-in name collisions are rejected."),
    "register_native_model": ("Register model-specific native array/template policies.", "name, NativeModel with required validate callback and optional read/template/phase/field callbacks; aliases.", "Registered NativeModel contract."),
    "register_serializer": ("Register a native serialization backend.", "name, serialize(temporary_path, arrays, template) callback and optional aliases.", "Registered serializer callable. The callback must write exactly the supplied temporary file."),
    "validate_file": ("Validate a canonical saved bulk product.", "path and optional explicit format.", "OutputValidationReport; require_valid() raises if its checks fail. Does not perform source/PSD convergence analysis."),
    "write_formatted_optical_output": ("Render a canonical product as a configured text table.", "path: destination/stem; data: supported result, canonical mapping or file; format_spec: OpticalTableFormat/mapping/specification input; encoding.", "Path or tuple of Paths for component-split output. Uses explicit column scale/transform conventions."),
    "load_optical_table_format": ("Load a text-table formatting contract.", "path: JSON or trusted Python specification defining optical_table_format.", "OpticalTableFormat; Python specifications execute code."),
    "export_bulk_optics": ("Write custom NetCDF/HDF5 layouts without recalculating optics.", "data: supported bulk result/grid/mapping/canonical file. output: layout mapping, outputs collection or trusted Python/JSON config. output_dir selects base; overwrite controls existing custom files.", "dict with outputs and per-file results/validation. Rejects canonical-source overwrite and unsupported/lossy conversions."),
    "write_rttov13_bulk_tables": ("Export fixed-PSD RTTOV13-style aerosol/cloud tables.", "result: supported complete spectrum; directory: destination; moment count, material densities and phase normalization must match the scientific contract.", "Manifest mapping and files. High-level descriptive/ZJU cloud names require reader adaptation."),
    "write_rttov14_bulk_tables": ("Export fixed-population RTTOV14 version-4 tables.", "data: supported table result or canonical file with required sibling report.json; directory; moment/density/phase settings.", "Manifest mapping and aertable/hydrotable files for the implemented thermal-IR subset."),
    "validate_rttov14_optical_table": ("Validate the fixed-population RTTOV14 output subset.", "path: emitted version-4 NetCDF optical table.", "Validation mapping; checks source-schema/physical invariants, not a compiled simulation."),
    "build_rttov14_lookup_tables": ("Compute retained size/RH/temperature RTTOV14 master tables.", "wavelengths, local source_paths, effective_radii_um, relative_humidity_percent, ice_temperatures_k and output_dir are explicit. bins/moments, branch, overrides and progress control calculation.", "Manifest mapping and master table files. RH here is explicitly percent. Requires downstream slicing/adaptation where stock axes differ."),
    "write_rttov14_lookup_slice": ("Select exact master-grid states for supported stock runtime axes.", "master_path, output_path; aerosol_effective_radii_um and ice_temperature_k select exact nodes.", "Lookup validation mapping; writes output_path without inventing interpolated states."),
    "validate_rttov14_lookup_table": ("Validate a retained/sliced RTTOV14 lookup table.", "path: lookup NetCDF file.", "Validation mapping for the implemented lookup schema; distinct from the fixed-population validator."),
    "rename_rttov14_species": ("Copy a table with explicit particle names.", "source, destination, output_names mapping/sequence as accepted by the table naming contract.", "Mapping identifying output/names; writes a copy while preserving optical arrays."),
    "write_arts_bulk_tables": ("Export totally-random ARTS version-3 SSD XML for fixed PSDs.", "data, output_dir, reference_temperature_k and phase_normalization. Requires complete six-element phase data and concentration metadata.", "Manifest mapping and one effective SSD XML product per supported population."),
    "validate_arts_bulk_table": ("Validate an emitted ARTS SSD tensor product.", "path and normalization_tolerance for integrated Z11 closure.", "Validation mapping; unsupported schema/normalization raises."),
    "write_crtm_ir_bulk_tables": ("Export the implemented CRTM IR fixed-population subset.", "data, output_dir and material_densities_kg_m3; optional growth_factors and phase_normalization.", "Manifest mapping and IR table files; does not create a complete arbitrary native CRTM CloudCoeff dataset."),
    "validate_crtm_ir_optical_table": ("Check the emitted CRTM IR subset.", "path: emitted IR table.", "dict including valid and native_crtm_compatible=False; does not claim native compiled-reader acceptance."),
    "load_single": ("Load one physical optical slice from a native file.", "path; include_phase_matrix; size_dataset and coordinate_indices for native axes; cext_mode and wavelength_um for physical interpretation; explicit NaN-asymmetry policy.", "SingleParticleOptics in physical units for the selected slice; does not preserve every native variable as a generic file reader."),
    "interpolate_nodes": ("Interpolate already-loaded optical nodes within supported coordinates.", "particle_type, OpticalNode sequence, target_coordinates; optional output size/angle grids, sparse-power and phase-normalization policy.", "InterpolatedOpticalProduct with physical optics and neighbor provenance."),
    "interpolate_sources": ("Load local source requests and interpolate physical optics.", "particle_type, OpticalSourceRequest sequence and target_coordinates; kwargs follow interpolate_nodes.", "InterpolatedOpticalProduct; invalid/incompatible source support raises."),
    "default_refractive_index_paths": ("Locate packaged material tables for a profile/scheme.", "particle_type and explicit/default ri_scheme.", "Mapping from material role to Path; location is not proof the target has covered source optics."),
    "wavelength_to_um": ("Convert wavelength/wavenumber to positive micrometres.", "value: supported scalar input; unit: um, nm or cm-1.", "float in um; invalid/nonpositive inputs raise."),
    "interpolate_downloaded_particle_series": ("Write native-schema derived files from selected downloads.", "downloaded_sources, targets and processing records from retrieval; output_dir; overwrite/tolerance/progress and phase-compatibility controls.", "List of InterpolatedFileResult records; writes derived products while preserving native source schemas. Prefer configured retrieve for ordinary use."),
    "verify_native_schema": ("Compare a derived native file to its template schema.", "path: derived file; template_path: authoritative source template.", "bool indicating complete compatible dimensions, variables, dtypes and variable attributes; reads files."),
    "plot_single_particle_optics": ("Create live single-particle scalar and phase figures.", "optics: loaded SingleParticleOptics; optional scalar/phase output paths, selected radii, title, show, dpi and style.", "Figure mapping with properties/phase entries; requested paths save figures."),
    "plot_single_scattering": ("Inspect a single-particle file or loaded slice with outputs.", "source: file or SingleParticleOptics; output_dir/style/show; wavelength_um and coordinate_indices apply to file loading.", "dict with output_dir, files and inspection; writes figures, CSV and inspection report."),
    "plot_bulk_optics": ("Inspect existing bulk products without recalculation.", "source: supported canonical file/mapping/grid/optics; output_dir, show and style.", "dict with files, report_file, figures and inspection, including fixed/varying axis selections."),
    "lognormal_psd": ("Construct CDF-integrated lognormal bin counts.", "rg_um: geometric mean radius; sigma_g: geometric standard deviation; concentration; finite radius_range_um, bins and preserve/renormalize policy.", "SizeDistribution on volume-equivalent radii with probability/realized-moment metadata."),
    "gamma_psd": ("Construct CDF-integrated gamma bin counts.", "effective_radius_um=M3/M2; effective_variance between 0 and 0.5; concentration, finite bounds, bins and normalization policy.", "SizeDistribution with represented-bin counts and parent/realized metadata."),
    "check_size_coverage": ("Inspect common physical support of a population/PSD.", "particle_type, local source_paths, typed PSD, wavelength/unit and profile/ensemble/RI/size-definition inputs; truncation_policy.", "JSON-compatible mapping with source/common radius bounds, bin coverage, retained/lost concentration and policy."),
    "prepare_scheme_dependencies": ("Prepare source queries, downloads and verified manifests.", "config: Scheme; workspace, offline and download (default True), schema-validation/session/transfer controls; optional custom searcher/downloader and reuse directories.", "DependencyPlan with readiness/issues and manifest paths. Can download by default; use root plan or download=False for previews."),
    "build_dependency_queries": ("Compile deterministic queries from named scheme populations.", "config: normalized Scheme.", "Tuple of DependencyQuery records; compilation does not prove remote availability."),
    "select_shape_grid_sources": ("Select joint shape/RI source stencils without mixing revisions.", "objects: catalog records; family: particle family; points: resolved RI targets; targets: shape targets.", "(selected objects, resolution-record tuple, interpolation-required bool). Specialist selection stage; no numerical integration."),
    "inspect_source_file": ("Check native source identity and required variables.", "path: local L1 file; particle_type: profile name or ParticleProfile.", "SourceInspection with validation result, issues and source metadata."),
    "get_particle_adapter": ("Instantiate the selected registered particle adapter.", "particle_type: name/alias.", "ParticleAdapter implementing resolution/interpolation capabilities."),
    "resolve_particle_sources": ("Resolve local particle files to minimal native source nodes.", "particle_type, local source_paths; kwargs include wavelength/unit, parameters, RI tables, size definition and phase loading requirements.", "AdapterResolution with target coordinates, selected source nodes and provenance."),
    "resolve_plan_component_sources": ("Resolve one named population from a verified dependency plan.", "plan: DependencyPlan; component_name: saved population name; kwargs supply adapter-resolution inputs.", "AdapterResolution for that component; absent/unready source information raises."),
    "interpolate_particle": ("Resolve, load and interpolate one particle-family request.", "particle_type, local source_paths, optional output size/angle grids and phase policy; kwargs provide wavelength, parameters, RI tables and size definition.", "InterpolatedOpticalProduct with physical optical values and adapter provenance."),
    "load_native_output_template": ("Read an explicit native-output JSON template.", "path: JSON template file.", "Template mapping; reading is separate from model-array validation."),
    "native_template_from_reference": ("Inspect a supported reference file's native layout.", "path: reference file; model: registered native model identifier.", "Template mapping from the model's supported inspection callback."),
    "read_native_optical_arrays": ("Read arrays from a supported native model file.", "path and registered model identifier.", "Model-specific array mapping; unsupported read capability raises."),
    "arts_output_template": ("Construct a totally-random ARTS SSD template.", "n_frequency, n_temperature, n_angle: required axis lengths.", "Template mapping; optical arrays must be supplied separately."),
    "write_native_optical_output": ("Serialize explicitly supplied arrays against a native/custom template.", "path: destination; data: array mapping; template: supported template input; overwrite controls replacement.", "Path; validates/serializes to a temporary file before replacement. Does not compute absent physics."),
    "crtm_cloud_output_template": ("Construct the full release-3 CRTM CloudCoeff layout.", "dimensions: explicit model dimension mapping; binary selects format; byte_order and version set binary/release fields.", "Template mapping requiring the complete prescribed arrays, distinct from the high-level IR subset."),
    "rttov13_aerosol_output_template": ("Construct a RTTOV13 aerosol HDF5 template.", "n_channels and species; moment count, optional phase angles/solar channels and explicit naming convention.", "Template mapping; callers supply arrays in the correct sensor-channel order."),
    "arts_arrays_from_bulk": ("Convert a canonical population to ARTS-normalized arrays.", "data and selected component; number_density_m3 is explicit; temperature_k supplies the effective-state temperature when needed.", "Array mapping with ARTS frequencies, tensors and normalization; requires complete phase information."),
    "bulk_model_fields": ("Convert bulk coefficients to a native model's concentration convention.", "bulk: BulkOptics; model: registered policy; explicit mass_concentration_kg_m3 or number_density_m3 as required.", "Model-specific optical-field mapping; missing normalization inputs raise."),
    "scalar_phase_to_model": ("Project scalar P11 into a model's phase representation.", "angles_degrees and p11; model, max_moments, quadrature/hemisphere resolution and normalization tolerance.", "Model-specific phase/BPR/coefficient mapping. Does not generate missing vector generalized-spherical coefficients."),
    "default_bulk_assumptions": ("Resolve editable built-in/extension reference assumptions.", "particle_type, optional local source_paths, and preset name.", "Settings mapping with shape/environment/PSD assumptions and resolved support-dependent defaults where available."),
    "radius_moments": ("Measure realized radius moments of represented bin counts.", "psd: SizeDistribution on the intended physical radius definition.", "Mapping with number-mean radius, effective radius/variance and realized moment information."),
    "gamma_radius_bounds": ("Compute finite gamma radius bounds from parent parameters.", "effective_radius_um and effective_variance.", "(lower_um, upper_um), based on the implemented tail-probability cutoffs; not source coverage."),
}

SUPPLEMENTARY = {
    "zju_scatt_interface.io.native": ["load_native_output_template", "native_template_from_reference", "read_native_optical_arrays", "arts_output_template", "write_native_optical_output", "crtm_cloud_output_template", "rttov13_aerosol_output_template", "arts_arrays_from_bulk", "bulk_model_fields", "scalar_phase_to_model"],
    "zju_scatt_interface.bulk.defaults": ["default_bulk_assumptions"],
    "zju_scatt_interface.psd.analytical": ["radius_moments", "gamma_radius_bounds"],
}


def inventory():
    functions, classes, unavailable = OrderedDict(), OrderedDict(), []
    for path in sorted((ROOT / "src").rglob("__init__.py")):
        if "cli" in path.parts or "__all__" not in path.read_text(encoding="utf-8"):
            continue
        parts = path.parent.relative_to(ROOT / "src").parts
        module_name = ".".join(("zju_scatt_interface", *parts))
        module = importlib.import_module(module_name)
        for name in module.__all__:
            try:
                value = getattr(module, name)
            except (AttributeError, ImportError) as exc:
                unavailable.append((f"{module_name}.{name}", str(exc)))
                continue
            group = functions if inspect.isfunction(value) else classes if inspect.isclass(value) else None
            if group is not None:
                group.setdefault(value, []).append(f"{module_name}.{name}")
    for module_name, names in SUPPLEMENTARY.items():
        module = importlib.import_module(module_name)
        for name in names:
            functions.setdefault(getattr(module, name), []).append(f"{module_name}.{name}")
    return functions, classes, unavailable


def signature(value, name):
    sig = inspect.signature(value)
    text = str(sig)
    text = re.sub(r"<function ([^ >]+) at 0x[0-9A-Fa-f]+>", r"<callback:\1>", text)
    text = re.sub(r"<class '([^']+)'>", r"\1", text)
    text = re.sub(r"zju_scatt_interface\.[A-Za-z_.]+\.", "", text)
    if len(name + text) < 115:
        return name + text
    # Split only the top-level parameter string; nested generics/defaults stay intact.
    level, quote, parts, start = 0, None, [], 1
    for pos, char in enumerate(text[1:], 1):
        if quote:
            if char == quote and text[pos-1] != "\\": quote = None
        elif char in "\"'": quote = char
        elif char in "([{": level += 1
        elif char in "]}": level -= 1
        elif char == ")":
            if level == 0:
                parts.append(text[start:pos].strip())
                return name + "(\n    " + ",\n    ".join(p for p in parts if p) + ",\n)" + text[pos+1:]
            level -= 1
        elif char == "," and level == 0:
            parts.append(text[start:pos].strip()); start = pos + 1
    return name + text


def method_note(cls, name, fn):
    if name == "to_dict": return ("Serialize the object's recorded fields without recomputation.", "No scientific inputs beyond the existing instance.", "Mapping containing the recorded fields and available nested diagnostics.")
    if name in {"from_dict", "from_mapping", "from_value"}: return ("Construct/normalize this type from a supported representation.", "value: the declared mapping/value; base_dir/index, when present, resolve paths and component identity.", f"{cls.__name__} or the base component type indicated by the signature; validation errors raise. Inherited component parsers return the generic ParticleComponent contract.")
    if name == "write_json": return ("Save this object's JSON representation.", "path: destination; indent: formatting control.", "Path; writes a file, without recalculating optics.")
    if cls.__name__ == "Scheme" and name in {"plan", "build", "validate"}:
        returns = {"plan": "DependencyPlan; may inspect remote listings and write manifests, but never downloads optical files.", "build": "BulkDataset; kwargs accepts plan= and supported build options; call write to save.", "validate": "Tuple of validated dependency queries; does not prove source availability."}
        return (f"{name.capitalize()} this existing scheme.", "The existing Scheme; kwargs, where present, follows the corresponding root operation.", returns[name])
    if name == "require_valid": return ("Require every recorded file-quality check to pass.", "Existing validation report instance.", "The same report on success; ValueError on invalid output.")
    if name == "from_shapes": return ("Preserve joint shape states in a normalized weighted ensemble.", "shapes: mapping sequence; weights: matching explicit fractions or None for equal weights.", "WeightedShapeEnsemble; incompatible lengths/weights raise.")
    if name == "normalized": return ("Create an explicitly concentration-rescaled PSD.", "number_concentration_cm3: requested represented concentration.", "New SizeDistribution; source coordinate interpretation is preserved.")
    if name == "convert_size_definition": return ("Convert PSD radii using verified geometry.", "target_definition; converter callback and geometry_source when a conversion is needed.", "New SizeDistribution with recorded geometry; no universal radius-conversion factor is assumed.")
    if name == "remap": return ("Conservatively remap counts to another size grid.", "target_size/unit, explicit truncation policy and outside tolerance.", "(SizeDistribution, RemapReport) with retained/lost concentration.")
    if name == "from_callable": return ("Evaluate a function as represented-bin values on explicit size coordinates.", "size and function(radius); unit/size definition/source and PSD options. Integrate a differential density into bin counts beforehand.", "SizeDistribution; does not infer measurement-bin integrals.")
    if name.startswith("from_") and cls.__name__ == "SizeDistribution": return ("Load a PSD with explicit coordinate/count conventions.", "path and optional field names, size unit/definition, count units and parsing options shown in the signature.", "SizeDistribution; does not silently normalize measured counts.")
    if name == "to_csv": return ("Write represented radii and bin counts with PSD metadata.", "path: CSV destination.", "Path; input concentration is retained.")
    if name == "save" and cls.__name__ == "PopulationResult": return ("Save a population and its diagnostic bundle.", "directory; optional PSD, component/source metadata, NetCDF filename/title, include_members, and opt-in normalized dust L2 export.", "Output/summary mapping; writes validated NetCDF, CSV, JSON and supplied PSD. L2 mode has additional scientific requirements.")
    if name == "save" and cls.__name__ == "BulkTableResult": return ("Save a table result with its assumptions report.", "directory and selected formats ('nc', 'csv').", "Output-path mapping; writes selected data and report artifacts.")
    if name == "write" and cls.__name__ == "DependencyPlan": return ("Save the dependency manifest to its workspace location.", "The existing plan and its workspace.", "Path of the written manifest.")
    if name == "create" and cls.__name__ == "WorkspaceLayout": return ("Create a dependency workspace layout.", "root and scheme output path.", "WorkspaceLayout; creates cache/work/manifest directories and resolves output location.")
    if name == "parameter": return ("Look up one profile coordinate specification.", "name: canonical parameter or supported alias.", "ParameterSpec with role, unit, ranges and source representation; unknown names raise KeyError.")
    if name == "from_csv" and cls.__name__ == "RefractiveIndexTable": return ("Read a material's wavelength-dependent complex indices.", "path; optional wavelength unit and real/imaginary/wavelength column names.", "RefractiveIndexTable; verifies supported CSV representation.")
    if name == "interpolate" and cls.__name__ == "RefractiveIndexTable": return ("Interpolate a material index at a physical wavelength.", "wavelength_um; extrapolate is explicit and defaults False. Research workflows should remain within verified coverage.", "ComplexRefractiveIndex containing real/imaginary values.")
    if name == "interpolate": return ("Load/align the resolution's selected source nodes and interpolate optics.", "Optional output size/angle grids, source size grids and explicit invalid-point/phase policies.", "InterpolatedOpticalProduct with source provenance.")
    if name == "resolve": return NOTES["resolve_particle_sources"]
    if name == "to_request": return ("Convert an adapter-selected node to a loading request.", "include_phase_matrix and size_dataset explicitly control loading.", "OpticalSourceRequest for the selected native source.")
    if name == "build": return NOTES["build_grids"] if cls.__name__ == "MultiBulkScheme" else NOTES["build_grid"]
    if name == "raise_for_status": return ("Require selected retrieval completion conditions.", "download, require_matches and require_products choose necessary checks.", "The same RetrievalResult on success; ScattError if status/download/product requirements fail.")
    if name == "write_manifest": return ("Write selected source objects to a catalog manifest.", "path and optional format_name.", "Path of the manifest.")
    if name == "write_report": return ("Save a standard retrieval result report.", "path: JSON destination.", "Path of the report.")
    client = {
        "get_bytes": ("Read an HTTP resource.", "url: service/object URL.", "bytes; performs network I/O."),
        "get_json": ("Read a JSON HTTP response.", "url.", "dict; performs network I/O."),
        "post_json": ("Submit a JSON service request.", "url, payload and optional headers.", "Response dict; performs a network mutation according to the endpoint."),
        "list_page": ("List one object-store page.", "prefix, optional delimiter and continuation marker.", "ListPage; performs a network listing."),
        "iter_objects": ("Iterate objects across listing pages.", "prefix and optional on_page callback.", "Iterator of RemoteObject; consumes network pages lazily."),
        "list_directory": ("List immediate remote directories/objects.", "prefix.", "(list[RemoteDirectory], list[RemoteObject], page count)."),
        "stat_object": ("Inspect remote object metadata.", "key: remote object key.", "RemoteObject or None when absent; performs a metadata request."),
        "validate_session": ("Check remote session validity.", "token: session secret.", "bool; network validation, without saving a new session."),
        "register": ("Submit a registration payload.", "payload: researcher identity/consent fields.", "Session token string (secret); network registration. Prefer register_direct for local persistence."),
        "track_event": ("Record an authorized usage event.", "token, object key and event_type.", "None; performs a tracking request."),
    }
    if cls.__name__ == "ApiClient" and name in client: return client[name]
    raise ValueError(f"Missing method semantics: {cls.__name__}.{name}")


def generate():
    functions, classes, unavailable = inventory()
    missing = [fn.__name__ for fn in functions if fn.__name__ not in NOTES]
    if missing: raise ValueError(f"Missing function semantics: {missing}")
    sections = OrderedDict()
    for fn, aliases in functions.items():
        namespace = aliases[0].rsplit(".", 1)[0]
        sections.setdefault(namespace, []).append((fn, aliases))
    lines = ["# Function and object reference", "",
        '<img src="assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">', "",
        "This reference covers every resolvable function explicitly exported by the root",
        "package and its non-CLI public namespace `__all__` lists, plus the documented",
        "native-output, default-assumption and analytical-moment helpers. Aliases share",
        "one entry. Internal underscore helpers and CLI implementation callbacks are not",
        "the research API; use the [manual](USER_MANUAL.md) for commands and examples.", "",
        f"Coverage: **{len(functions)} distinct functions**, **{len(classes)} exported types**",
        "(including exceptions/enums), and the non-inherited public methods listed below.",
        "Inherited component parsing/serialization methods are documented once on",
        "`ParticleComponent`; leaf component constructors remain listed individually.", "",
        "Signatures/defaults are inspected from the current source. A `*` starts",
        "keyword-only arguments; omitted return annotations are supplemented by the",
        "reviewed Returns text. Callback defaults are named without process addresses.",
        "A signature describes accepted arguments, not proof that a scientific target",
        "is available. Registration, optional dependencies and physical conventions",
        "still apply; see the [scientific reference](SCIENTIFIC_REFERENCE.md).", "",
        "## Contents", ""]
    for index, namespace in enumerate(sections, 1):
        lines.append(f"- [{namespace}](#functions-{index})")
    lines.append("- [Types and object methods](#types-and-object-methods)")
    if unavailable:
        lines.append("- [Known unavailable exports](#known-unavailable-exports)")
    lines.append("")
    for index, (namespace, entries) in enumerate(sections.items(), 1):
        lines += [f'<a id="functions-{index}"></a>', f"## {namespace}", ""]
        for fn, aliases in entries:
            purpose, inputs, returns = NOTES[fn.__name__]
            name = aliases[0].rsplit(".", 1)[1]
            lines += [f"### `{name}`", "", purpose, "", "```text", signature(fn, name), "```", "",
                      f"**Inputs:** {inputs}", "", f"**Returns:** {returns}", ""]
            if len(aliases) > 1:
                lines += ["**Also exported as:** " + ", ".join(f"`{a}`" for a in aliases[1:]) + ".", ""]
            if fn.__name__ == "retrieve_sources":
                from zju_scatt_interface.access.requests import make_retrieval_args
                lines += ["#### Forwarded retrieval keywords", "",
                    "The accepted `**parameters` names/defaults are shown below. This is",
                    "the argument contract used by the selector, not another recommended",
                    "research entry point. Target wavelengths trigger supported scientific",
                    "resolution; wavelength_range is a raw filename filter. File/count limits",
                    "must not truncate a required interpolation stencil. Session values are",
                    "secrets and should be supplied through local registration instead.", "",
                    "```text", signature(make_retrieval_args, "retrieval_keywords"), "```", ""]
    lines += ["## Types and object methods", "",
        "Constructor parameters below define the public fields/options. Constructors",
        "return an instance of the named type; most result types are normally obtained",
        "from operations rather than assembled by hand. Fields are not extra calls.", ""]
    method_count = 0
    for cls, aliases in classes.items():
        lines += [f"### `{cls.__name__}`", "", "**Import:** `" + aliases[0] + "`.", ""]
        doc = inspect.getdoc(cls) or ""
        if issubclass(cls, Exception):
            lines += [doc or "Exception raised by the matching workflow.", ""]
            continue
        if cls.__module__ == "zju_scatt_interface.config.particles" and cls.__name__ == "DataStructure":
            lines += ["Enum values: `grid_based`, `wavelength_based`; describes native database organization.", ""]
            continue
        # Dataclasses without a written docstring inherit a generated signature as doc.
        if doc and not doc.startswith(cls.__name__ + "("):
            summary = doc.split("\n\n")[0].replace("Phase-8 storage controls", "storage controls").replace("written Phase-8 product", "written canonical product")
            lines += [summary, ""]
        lines += ["```text", signature(cls, cls.__name__), "```", "",
                  f"**Inputs:** Constructor fields/defaults above; physical units and conventions are defined in the scientific reference. **Returns:** `{cls.__name__}` instance.", ""]
        for name, raw in cls.__dict__.items():
            if name.startswith("_") or isinstance(raw, property): continue
            fn = getattr(cls, name)
            if not (inspect.isfunction(fn) or inspect.ismethod(fn)): continue
            purpose, inputs, returns = method_note(cls, name, fn)
            method_count += 1
            lines += [f"#### `{cls.__name__}.{name}`", "", purpose, "", "```text", signature(fn, name), "```", "",
                      f"**Inputs:** {inputs}", "", f"**Returns:** {returns}", ""]
    if unavailable:
        lines += ["## Known unavailable exports", "",
            "The following declared exports do not resolve in this source snapshot.",
            "They require an implementation or export-binding correction before use.", ""]
        for name, error in unavailable:
            lines.append(f"- `{name}`: {error}.")
    output = ROOT / "docs" / "FUNCTION_REFERENCE.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output}: {len(functions)} functions, {len(classes)} types, {method_count} methods; {len(unavailable)} unavailable exports")


if __name__ == "__main__":
    generate()
