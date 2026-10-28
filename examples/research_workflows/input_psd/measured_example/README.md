# Example measured-PSD input format

<img src="../../../../docs/assets/LOGO_ZJU_SCATT.png" alt="ZJU-SCATT logo" width="420">

These eight CSVs contain **synthetic test values**, not actual measurements.
Each species has its own PSD. Replace the CSV contents with your observations;
the runner reads the files and never regenerates or overwrites them.

- `radius_um`: physical volume-equivalent sphere radius in micrometers.
- `number_per_bin_cm3`: number concentration in that size bin, in cm^-3.
  Summing this column gives the species' total number concentration.

The API's historical name `dndr` denotes per-bin counts here. Do not supply
`dN/dr`, `dN/dD`, or `dN/dlog10(D)` directly. For a measured differential
distribution, integrate over each instrument bin (or multiply the bin-average
density by its corresponding linear/logarithmic bin width). Convert m^-3 to
cm^-3 by dividing by 1e6.

For volume-equivalent diameter measurements, divide diameter by two. Optical
or aerodynamic instrument diameter requires a justified conversion to the
volume-equivalent coordinate; dividing it by two alone is insufficient.

Sizes must be positive and increasing, counts nonnegative, and total count
positive. The current interface infers bin edges from arithmetic midpoints
between centers, extrapolating the two outer edges. These inferred edges must
fit the common source size coverage across all wavelengths and shapes.
It does not currently accept arbitrary measured bin edges in this workflow.

With `coverage_policy="error"`, uncovered bins cause an error. The program
does not silently clip or normalize measured counts. Default analytical PSDs
are replaced by these files; default shape/RI/environment assumptions remain.
For shape ensembles the supplied N is the total across the ensemble, divided
among shapes by their weights. Species are calculated independently.
