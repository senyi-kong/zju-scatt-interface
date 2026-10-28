"""Construct the parser from built-in and explicitly registered commands."""

import argparse

from zju_scatt_interface.cli.builtin_commands import build_parser as builtin_parser
from zju_scatt_interface.extensions.commands import install_commands


def build_parser():
    parser = builtin_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    install_commands(subparsers)
    return parser
