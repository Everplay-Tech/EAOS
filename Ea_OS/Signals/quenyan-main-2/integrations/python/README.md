# Python packaging (setuptools) integration

Use `integrations/python/quenyan_build.py` to integrate the Quenyan
encoder into standard `setup.py` builds:

```python
# setup.py
from setuptools import setup
from integrations.python.quenyan_build import build_py

setup(
    name="example",
    packages=["example"],
    cmdclass={"build_py": build_py},
)
```

### Recommended workflow

1. Run `quenyan init --generate-keys` in the repository root.
2. Add the generated `.quenyan/keys/master.key` to CI secrets, not to
   version control.
3. Build wheels with
   `python -m build --wheel -- -b build -o dist --quenyan-keyfile=.quenyan/keys/master.key`.
4. Consumers installing the wheel can use
   `python -m quenyan.cli decode ...` or the IDE integration to inspect
   packages locally.

The helper honours `QUENYAN_CLI` to point at alternative executables
and falls back to `quenyan` on `$PATH`.
