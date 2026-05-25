#!/usr/bin/env python3
"""
Allow running agent as a module: python -m agent
"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
