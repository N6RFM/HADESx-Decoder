# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Compatibility shim: `unne1b.genesis` is `hadesx.genesis` (the package was renamed). Deprecated."""
import importlib
import sys

_new = importlib.import_module('hadesx.genesis')
if __name__ == '__main__':
    pass
else:
    sys.modules[__name__] = _new          # `import unne1b.genesis` gives the very same module object as `import hadesx.genesis`
