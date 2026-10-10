#!/usr/bin/env python3
"""Thin entry point: `python3 main.py <command>` is `python3 litholog.py <command>`.

The implementation is the single standard-library file ``litholog.py`` next to
this shim. This file exists only so tooling that looks for a ``main.py`` at the
project root finds LithoLog; both invocations accept exactly the same arguments.
"""

from litholog import main

if __name__ == "__main__":
    raise SystemExit(main())
