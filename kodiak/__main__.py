#!/usr/bin/env python3
"""
Main entry point for running Kodiak as a module: python -m kodiak
"""

import sys
from kodiak.cli import main

if __name__ == "__main__":
    sys.exit(main())