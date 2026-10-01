"""Compare sprite contracts without depending on atlas packing."""

__version__ = "0.1.0"

from .core import ContractError, compare, load_atlas

__all__ = ["ContractError", "compare", "load_atlas", "__version__"]
