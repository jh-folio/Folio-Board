"""Rename compatibility contract: the OS keyring service name never changes.

plan §4.2 keeps `SECRET_STORE_SERVICE` as the literal `"Folio OS"` on purpose —
renaming it would make every API key a user already stored under the old
service name invisible to the app, indistinguishable from "never entered one."
A future migration (new-first, legacy-fallback, copy-on-success) is an open
decision (plan §10), but until that ships, this string must not move.
"""
from features.llm_settings.client import SECRET_STORE_SERVICE


def test_secret_store_service_name_is_unchanged_by_the_rename():
    assert SECRET_STORE_SERVICE == "Folio OS"
