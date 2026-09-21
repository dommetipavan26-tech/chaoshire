"""Single source of truth for the build facts the landing page and README quote.

Every number a reviewer can compare against the repository lives here exactly
once. ``/api/meta`` serves it, so ``index.html`` renders it instead of
hardcoding a string that can drift from ``chaoshire.__version__`` — the failure
mode that left the landing page advertising v0.21.0 while the package said
0.22.0 and a browser test asserted the stale value.

``scripts/check_build_info.py`` runs in CI and fails the build when
:data:`AUTOMATED_TESTS` or :data:`PACKAGE_COVERAGE` stop matching what pytest
actually reports. Everything else in this module is derived at import time from
the running package, so it cannot drift by construction.
"""

from . import __version__
from .chaos import CHAOS_TESTS
from .data import DEMO_DATA
from .models import MODEL_META

#: Committed package version. Never duplicated anywhere else.
VERSION = __version__

#: Verified by ``scripts/check_build_info.py`` against a real pytest run.
AUTOMATED_TESTS = 201

#: Verified by ``scripts/check_build_info.py`` against a real coverage report.
PACKAGE_COVERAGE = "98.3%"

#: Derived: cannot drift.
SERVICE_WORKER_CACHE = f"chaoshire-v{VERSION.replace('.', '')}"
CHAOS_EXPERIMENTS = len(CHAOS_TESTS)
REFERENCE_MODELS = len(MODEL_META)
DEMO_CANDIDATES = len(DEMO_DATA)


def build_info() -> dict[str, object]:
    """The payload ``/api/meta`` serves as ``build``."""
    return {
        "version": VERSION,
        "automated_tests": AUTOMATED_TESTS,
        "package_coverage": PACKAGE_COVERAGE,
        "chaos_experiments": CHAOS_EXPERIMENTS,
        "reference_models": REFERENCE_MODELS,
        "demo_candidates": DEMO_CANDIDATES,
        "verification": (
            "version, model count, experiment count and fixture size are derived from "
            "the running package; the test and coverage figures are checked against a "
            "real pytest run by scripts/check_build_info.py in CI."
        ),
    }
