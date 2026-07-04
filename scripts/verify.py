#!/usr/bin/env python3
"""PokeCham verifier CLI facade.

v29.43 keeps the public command interface stable:
    python3 scripts/verify.py <command> ...

Implementation lives under scripts/pokecham_verify/ so engine modules can be
maintained/tested without growing this wrapper.
"""
from pokecham_verify.cli import main

if __name__ == "__main__":
    main()
