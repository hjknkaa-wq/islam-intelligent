"""Domain package scaffold."""

from .span_builder import (
    create_span,
    validate_span,
    verify_span_hash,
    extract_snippet,
    compute_snippet_hash,
    get_prefix_suffix,
)

__all__ = [
    "create_span",
    "validate_span",
    "verify_span_hash",
    "extract_snippet",
    "compute_snippet_hash",
    "get_prefix_suffix",
]