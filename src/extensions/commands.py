"""Explicit command contributions, installed when the application builds its parser."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from zju_scatt_interface.extensions.registry import ExtensionError, NamedRegistry


@dataclass(frozen=True)
class Command:
    """configure(parser), run(args, client) -> exit code; validate(args) optional."""

    name: str
    help: str
    configure: Callable
    run: Callable
    validate: Callable | None = None


_commands = NamedRegistry[Command]("command")


def register_command(command: Command):
    if not isinstance(command, Command):
        raise ExtensionError("Expected a Command")
    if not callable(command.configure) or not callable(command.run):
        raise ExtensionError("Command.configure and run must be callable")
    if command.validate is not None and not callable(command.validate):
        raise ExtensionError("Command.validate must be callable")
    if not isinstance(command.name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", command.name):
        raise ExtensionError(
            "Use a lowercase command name with letters, digits, hyphens or underscores"
        )
    from zju_scatt_interface.cli.builtin_commands import builtin_command_names

    if NamedRegistry.normalize(command.name) in {
        NamedRegistry.normalize(name) for name in builtin_command_names()
    }:
        raise ExtensionError(f"Command shadows a built-in: {command.name}")
    return _commands.register(command.name, command)


def install_commands(subparsers):
    for name, command in _commands.items():
        parser = subparsers.add_parser(command.name, help=command.help)
        parser.set_defaults(timeout=30.0, retries=0, insecure=False, quiet=True)
        command.configure(parser)
        parser.set_defaults(
            func=command.run, extension_validate=command.validate, extension_command=True
        )
