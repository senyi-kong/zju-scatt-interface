---
name: zju-scatt-research
description: Prepare, execute, and inspect ZJU-SCATT optical-data retrieval and PSD-integrated research workflows using its installed Python API or CLI. Use for ZJU-SCATT data, schemes, particle optics, and bulk optical products; not for general literature research.
---

# ZJU-SCATT research

<img src="../../assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

Help the researcher obtain reproducible optical results through the existing
interface. Use the interface for scientific calculations and retain its diagnostics.

## Locate the contract

Identify the active environment and project documentation. Read `docs/FUNCTION_REFERENCE.md`
and `docs/USER_MANUAL.md` from the matching source checkout when available.
Find the checkout from the supplied project path or `zju_scatt_interface.__file__`;
do not assume that documentation is installed in a wheel. If needed, request the
matching docs path while inspecting installed CLI help and signatures.

Check package version, import location, CLI help, and `doctor --offline --json`.
The current release is `1.0.0`; match documentation and callable APIs to the active
installation when adapting scripts from earlier development layouts.
Prefer `python -m zju_scatt_interface` to bind CLI calls to the chosen interpreter.
Do not import retired root functions or copy examples from archived snapshots.

Reuse existing registration. Schema discovery and offline calculations also require
registration; help and offline diagnostics remain available without it. If missing,
have the researcher complete registration with their own information and consent.
Do not request tokens in chat or expose session files. Do not bypass registration.

Read the installed `bulk-opt schema --json`, narrowed by `--particle-type` when
appropriate. It is a domain reference, not a generic JSON Schema or proof of remote
availability. For execution details and task routing, read
[references/workflows.md](references/workflows.md).

## Resolve scientific choices

Establish particle/profile, spectrum and units, PSD convention/concentration, size
definition, relevant shape/environment coordinates, RI strategy and output needs.
Ask for unresolved choices that change the scientific meaning. Use a requested
preset or documented default transparently and record resolved values; do not
substitute demonstration recipe values for unspecified research inputs.

- Scheme `dndr` means counts per represented bin in `cm-3`, not `dN/dr`.
- Size inputs are radii; distinguish volume-equivalent and maximum-dimension radius.
  Differential distributions need actual measurement-bin integration. Do not invent
  bin edges or a particle-geometry conversion.
- RH is a fraction, temperature is K, wavelengths accept `nm`, `um`, or `cm-1`.
- Inspect the selected database's coordinate contract. RI-grid dust/BC and native
  wavelength profiles need different RI handling; BC has both database types.
- Preserve joint shape members/weights and separate named populations. Independent
  weighted parameters form a Cartesian product.

Read `docs/SCIENTIFIC_REFERENCE.md` and the relevant particle/PSD guide for
unfamiliar inputs. JSON is preferred for portable evaluated inputs. Python configs
execute code; review generated scripts and only load trusted configurations.

## Execute and verify

Validate input, compile a local dry-run, inspect dependency issues, then execute
within the researcher's requested scope. A normal plan may use the network and
write manifests but does not download optical data. `scheme-sources` and the
specialist dependency preparer can download; use public `plan` for previews.

Check command exit codes and reports. Query compilation does not establish source
coverage. Missing cached sources may be resolved by an online build; invalid
scientific choices require correction. For an unexplained failure, inspect its
report once and make a supported correction rather than retrying unchanged.

Do not silently enable truncation, extrapolate, normalize, change RI schemes,
select nearest data, disable QA, or discard failing members to obtain success.
Inspect population/member QA, convergence, PSD remapping, source provenance and
NaN boundaries. The CLI build summary does not include all detailed diagnostics;
retain Python results or population summaries when those are needed.

Distinguish input validity, source readiness, execution success and adequacy for
the scientific question. Report unchecked or unavailable diagnostics as such.
Deliver evaluated inputs, exact commands/environment, outputs, source identities,
resolved assumptions, reports and limitations. Never claim an unexecuted plan is
a completed calculation. Preserve existing research outputs unless replacement
is authorized; do not modify interface internals to make a research job pass.
