"""Console entry point: ``pcc`` command."""

import sys
from . import __main__ as _main


def cli():
    """Entry point for the ``pcc`` console script."""
    sys.exit(_main.main())


if __name__ == "__main__":
    cli()
