"""Artifact-native, rules-only Change Intelligence."""

from .service import decorate_candidate, strip_change_metadata

__all__ = ["decorate_candidate", "strip_change_metadata"]
