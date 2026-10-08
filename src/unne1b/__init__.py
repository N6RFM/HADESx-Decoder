# HADESx Decoder  -  https://github.com/N6RFM/HADESx-Decoder
# Authors: N6RFM, with Claude (an AI assistant made by Anthropic).
# Licence: MIT (see LICENSE).
"""Compatibility: the package was renamed to `hadesx` (HADESx Decoder). `import unne1b`, `unne1b.core`, `unne1b.cli`,
`python3 -m unne1b` and `python3 -m unne1b.report` still work.

Deprecated: use `hadesx`. This shim is kept for a release or two."""
import hadesx
from hadesx import *   # noqa: F401,F403

__version__ = hadesx.__version__
__all__ = list(getattr(hadesx, '__all__', []))
