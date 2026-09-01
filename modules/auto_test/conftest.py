"""Compatibility marker for the auto_test tree.

The root pytest configuration loads ``fixtures.harness_plugin`` as the only
fixture and hook entry point. Keeping this file free of fixtures and hooks is
intentional: pytest otherwise gives the module-local conftest precedence and
silently creates a second lifecycle with different scopes.
"""
