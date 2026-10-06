"""Compatibility shim: `unne1b.report` is `hadesx.report` (the package was renamed). Deprecated."""
import importlib
import sys

_new = importlib.import_module('hadesx.report')
if __name__ == '__main__':
    _new.main()
else:
    sys.modules[__name__] = _new          # `import unne1b.report` gives the very same module object as `import hadesx.report`
