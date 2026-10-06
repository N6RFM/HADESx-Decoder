"""Compatibility shim: `unne1b.iqfile` is `hadesx.iqfile` (the package was renamed). Deprecated."""
import importlib
import sys

_new = importlib.import_module('hadesx.iqfile')
if __name__ == '__main__':
    pass
else:
    sys.modules[__name__] = _new          # `import unne1b.iqfile` gives the very same module object as `import hadesx.iqfile`
