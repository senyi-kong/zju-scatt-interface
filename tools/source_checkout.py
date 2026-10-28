"""Load the flat src/ package for source-inspection tools without an installation."""
import importlib.util
from pathlib import Path
import sys


def load_source_package(project):
    name = "zju_scatt_interface"
    source = Path(project).resolve() / "src"
    existing = sys.modules.get(name)
    if existing is not None:
        if Path(existing.__file__).resolve() != source / "__init__.py":
            raise RuntimeError("A different ZJU-SCATT installation is already imported")
        return existing
    spec = importlib.util.spec_from_file_location(name, source / "__init__.py",
        submodule_search_locations=[str(source)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
