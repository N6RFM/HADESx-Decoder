"""Compatibility shim: `unne1b.cli` is `hadesx.cli` (the package was renamed). Deprecated."""
import importlib
import sys

_new = importlib.import_module('hadesx.cli')
if __name__ == '__main__':
    _new.main()
else:
    sys.modules[__name__] = _new          # `import unne1b.cli` gives the very same module object as `import hadesx.cli`
