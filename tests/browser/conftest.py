"""The real-browser suite uses the app's default demo configuration.

The API/core tests share an autouse fixture that sets an operator key and
turns rate limits off. Browser tests spawn their own server and should not
inherit those environment changes when the suites live under the same tree.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_state():
    """Override the parent fixture; browser tests manage their own server state."""
    yield
