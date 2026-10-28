"""Compare optical-grid sensitivity at fixed PSD with the legacy rebinning check.

Uses previously verified native sources; does not change outputs or diagnostics.
"""
import argparse
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from zju_scatt_interface.bulk import quality
from zju_scatt_interface.bulk.integration import integrate
from zju_scatt_interface.bulk.tables import _compute_table
from zju_scatt_interface.optics.interpolation import OpticalNode, _resample_node
from zju_scatt_interface.psd.models import SizeDistribution

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--psd-bins", type=int, help="Rebuild analytical PSDs at the same bounds and concentration")
    parser.add_argument("--wavelengths", nargs="+", type=float)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new output filename to preserve previous evidence.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='work_'+args.output.stem+'_', dir=args.output.parent))
    def deny_network(event, arguments):
        if event in {'socket.connect', 'socket.getaddrinfo'}:
            raise RuntimeError('Convergence investigation requires cached local inputs')
    sys.addaudithook(deny_network)
    saved = json.loads(args.report.read_text(encoding='utf-8'))
    records = []
    original = quality._convergence_check

    def compare(optics, distribution, full, **kwargs):
        legacy = original(optics, distribution, full, **kwargs)
        indices = list(range(0, len(optics.sizes), 2))
        if indices[-1] != len(optics.sizes)-1:
            indices.append(len(optics.sizes)-1)
        coarse = quality._slice_optics(optics, indices)
        values = _resample_node(OpticalNode({}, coarse), optics.sizes, [])
        reconstructed = replace(optics, extinction_cross_section=values['cext'],
            scattering_cross_section=values['csca'], asymmetry_factor=values['g'],
            absorption_cross_section=[e-s for e,s in zip(values['cext'], values['csca'])],
            phase_matrix=None)
        candidate, _ = integrate(reconstructed, distribution,
            database_size_definition=kwargs['database_size_definition'],
            truncation_policy=kwargs['truncation_policy'])
        errors = {name: quality._relative_error(getattr(full,name),getattr(candidate,name))
            for name in legacy.relative_errors}
        records.append({'family': full.metadata.get('particle_type'),
            'wavelength_um': full.metadata.get('wavelength_um'),
            'nodes': len(optics.sizes), 'legacy': legacy.to_dict(),
            'fixed_psd_errors': errors,
            'full_values': {name:getattr(full,name) for name in errors},
            'psd_bins': len(distribution.size_um),
            'number_concentration_cm3': distribution.number_concentration_cm3,
            'source_nodes_within_psd_centers': sum(distribution.size_um[0] <= r <= distribution.size_um[-1] for r in optics.sizes)})
        return legacy

    overrides = {family: entry['effective_parameters'] for family,entry in saved['species'].items()}
    # Preserve the report's finite population and shape definitions exactly.
    for family, entry in saved['species'].items():
        psd = entry['psd']
        overrides[family] = {**overrides[family], 'psd': SizeDistribution(
            psd['size'], psd['dndr'], size_unit=psd['size_unit'],
            size_definition=psd['size_definition'], metadata=psd['metadata'], gap_policy='allow')}
        if args.psd_bins:
            from zju_scatt_interface.psd.analytical import gamma_psd, lognormal_psd
            metadata = psd['metadata']
            common = dict(radius_range_um=metadata['radius_bin_edges_um'],
                number_concentration_cm3=psd['number_concentration_cm3'], bins=args.psd_bins,
                normalization='renormalize')
            if metadata['type'] == 'lognormal':
                refined = lognormal_psd(metadata['rg_um'], metadata['sigma_g'], **common)
            elif metadata['type'] == 'gamma':
                refined = gamma_psd(metadata['effective_radius_um'],metadata['effective_variance'],**common)
            else:
                raise ValueError('PSD refinement requires an analytical input, never replaces measured counts')
            overrides[family]['psd'] = refined
        if entry.get('shapes'):
            overrides[family]['shapes'] = entry['shapes']
    quality._convergence_check = compare
    try:
        table = _compute_table(species=tuple(saved['species']),
            wavelengths=args.wavelengths or saved['wavelengths_um'], preset=saved['preset'],
            overrides=overrides, source_paths={f:[s['path'] for s in e['sources']] for f,e in saved['species'].items()},
            workspace=work, progress=None)
        args.output.with_name(args.output.stem+'_table.json').write_text(json.dumps({
            'rows':table.rows, 'physical_qa_all_passed': all(
                check['qa']['passed'] for entry in table.report['species'].values() for check in entry['checks']),
            'source_report':str(args.report), 'workspace':str(work),
            'psd_bins_override':args.psd_bins},indent=2)+'\n')
    finally:
        quality._convergence_check = original
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(records,indent=2)+'\n')


if __name__ == '__main__':
    main()
