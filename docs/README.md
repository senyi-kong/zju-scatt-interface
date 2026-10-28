# ZJU-SCATT documentation

<img src="assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

ZJU-SCATT Interface provides Python and command-line workflows for selecting,
downloading, interpolating, integrating and inspecting optical-property data.

| Document | Use it to |
|---|---|
| [User manual](USER_MANUAL.md) | Install the interface, complete a first calculation, and use retrieval, PSDs, bulk schemes, plots, exports and AI assistance |
| [Function reference](FUNCTION_REFERENCE.md) | Look up callable signatures, parameter defaults, purposes, return values and result-object methods |
| [Scientific reference](SCIENTIFIC_REFERENCE.md) | Check particle coordinates, units, PSD conventions, interpolation policies, output schemas and model-format limitations |
| [Extension guide](EXTENDING.md) | Understand the extension lifecycle, choose an extension point, and follow a complete PSD calculation example |
| [Research skill](skills/zju-scatt-research/SKILL.md) | Give an AI assistant a compact workflow for using the same documented interface |

Read the manual in order for a first run. Use the two references while preparing
research inputs or inspecting results. Numerical examples illustrate the interface;
they are not recommended atmospheric populations.

The current source reports version `1.0.0`. Check the import location and available
operations when reusing scripts from earlier development snapshots.
The installed CLI's `--help` and `bulk-opt schema --json` describe that installation.
Registration is required for normal operations, including schema discovery and
offline calculations; help and offline diagnostics are available beforehand.

The release documentation deliberately excludes dated progress reports, architecture
audits, generated illustrations, verification logs, and superseded topic guides.
Those materials are development records rather than instructions for the released
interface.
