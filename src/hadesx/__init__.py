"""HADESx Decoder: HADES-family (UNNE-1B, HADES-SA, HADES-L) FSK telemetry, CODEC2 voice and SSDV picture decoder."""
from .core import *          # noqa: F401,F403  (single self-contained module, see core.py)
from .core import __all__ as _core_all  # noqa: F401

__version__ = "1.2.0"
