"""Compatibility shim: `unne1b.frontend` is `hadesx.frontend` (the package was renamed). Deprecated."""
import importlib
import sys

_new = importlib.import_module('hadesx.frontend')
if __name__ == '__main__':
    pass
else:
    sys.modules[__name__] = _new          # `import unne1b.frontend` gives the very same module object as `import hadesx.frontend`
