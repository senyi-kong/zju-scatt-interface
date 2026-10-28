"""Discover subpackages while mapping the public package directly onto src/."""
from pathlib import Path

from setuptools import find_packages, setup

source = Path(__file__).resolve().parent / "src"
setup(packages=["zju_scatt_interface", *[
    f"zju_scatt_interface.{name}" for name in find_packages(where=str(source))
]])
