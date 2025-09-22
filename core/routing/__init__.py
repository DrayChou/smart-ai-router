
"""Legacy routing package retained for backward compatibility."""

from core.router.size_filters import SizeFilter, parse_size_filter, apply_size_filters

__all__ = ["SizeFilter", "parse_size_filter", "apply_size_filters"]
