"""Download public ARTS/CRTM reference tables; record supplied RTTOV13 files.

Role:
    Reference-format utility

Inputs:
    Public reference locations and optional user-supplied RTTOV paths.

Outputs:
    Reference artifacts and SHA256 manifest; supplied RTTOV files stay in place.

Run:
    From the package root: python examples/download_native_references.py --help

Notes:
    Reference artifacts validate serialization independently of the user's production optical
    data.

Original example details:
    Download public ARTS/CRTM reference tables; record supplied RTTOV13 files.

    python examples/download_native_references.py --rttov-cloud PATH --rttov-aerosol PATH
    Existing downloads are retained. The manifest records exact SHA256 hashes.
    RTTOV files remain at the supplied paths (no bulk copy or deletion).
"""

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCES = {
    "ARTS_tmatrix.xml": "https://raw.githubusercontent.com/atmtools/arts/v2.6.x/controlfiles/artscomponents/tmatrix/TestTMatrix.tot-random.ssdREFERENCE.xml",
    "CloudCoeff_TAMU-07Sep2015.nc": "https://ftp.emc.ncep.noaa.gov/jcsda/CRTM/coefficients/CloudCoeff_TAMU-07Sep2015.nc",
    "CloudCoeff_TAMU-07Sep2015.bin": "https://ftp.emc.ncep.noaa.gov/jcsda/CRTM/coefficients/CloudCoeff_TAMU-07Sep2015.bin",
    "CloudCoeff_netCDF_IO.f90": "https://raw.githubusercontent.com/JCSDA/crtm/master/src/Coefficients/CloudCoeff/CloudCoeff_netCDF_IO.f90",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reference_data/rtm_formats",
    )
    parser.add_argument("--rttov-cloud", type=Path)
    parser.add_argument("--rttov-aerosol", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records = []

    def record(path, source):
        with path.open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        records.append(
            {
                "path": str(path.resolve()),
                "source": source,
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )

    for name, url in SOURCES.items():
        path = args.output / name
        if not path.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                path.write_bytes(response.read())
        record(path, url)
    for path in (args.rttov_cloud, args.rttov_aerosol):
        if path:
            record(
                path,
                "User-supplied RTTOV13 coefficient file; https://nwpsaf.eu/site/software/rttov/download/coefficients/",
            )
    manifest = {"recorded_utc": datetime.now(timezone.utc).isoformat(), "references": records}
    target = args.output / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
