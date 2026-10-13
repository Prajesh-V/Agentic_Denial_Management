#!/usr/bin/env python
"""Synthetic Data Factory CLI entrypoint."""

import sys

from backend.app.data_factory.cli import main

if __name__ == "__main__":
    sys.exit(main())
