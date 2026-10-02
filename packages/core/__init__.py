"""Cross-cutting primitives shared by every service and package.

Nothing in this package may import from another top-level package. `core` is the
bottom of the dependency graph, so it depends only on the standard library and
third-party libraries it declares itself.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
