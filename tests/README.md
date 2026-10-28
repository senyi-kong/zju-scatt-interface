# Running tests

From the project root, use an editable install:

```console
pip install -e .
python -m unittest discover -s tests -v
```

Run one test file:

```console
python tests/test_cli.py
```

An editable installation is required for source-tree tests. The source package is
mapped directly from `src/` to the installed import name `zju_scatt_interface`;
setting `PYTHONPATH=src` does not provide that mapping.
