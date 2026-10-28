"""Console entry point and command dispatch."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

import zju_scatt_interface.access.client as _domain_access_client
import zju_scatt_interface.cli.arguments as _domain_cli_arguments
import zju_scatt_interface.errors as _domain_errors


def validate_arguments(args: argparse.Namespace) -> None:
    if getattr(args, "extension_command", False):
        validator = getattr(args, "extension_validate", None)
        if validator is not None:
            validator(args)
        return
    if args.command not in {
        "plot",
        "scheme",
        "bulk-opt",
        "scheme-sources",
        "psd-check",
        "describe",
        "resolve-ri",
    }:
        _domain_cli_arguments.validate_arguments(args)


def main(argv: Optional[Sequence[str]] = None) -> int:
    from zju_scatt_interface.cli.parser import build_parser

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_arguments(args)
        from zju_scatt_interface.access.registration import check_cli_registration

        registration_token = check_cli_registration(args)
        insecure = getattr(args, "insecure", False)
        client = _domain_access_client.ApiClient(
            timeout=args.timeout,
            retries=args.retries,
            insecure=insecure,
            show_tls_warning=not bool(getattr(args, "quiet", False)),
        )
        client.registration_token = registration_token
        return int(args.func(args, client))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except (OSError, ValueError, _domain_errors.ScattError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
