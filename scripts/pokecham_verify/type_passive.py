"""v29.43 extraction seam.

This module is intentionally thin in v29.43: behavior remains in legacy.py while
public CLI compatibility and regression tests are stabilized. Future versions can
move the named functions here without changing scripts/verify.py commands.
"""
from .legacy import *  # noqa: F401,F403
