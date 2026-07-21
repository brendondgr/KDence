"""Sanity test proving the runner and package import work.

Replaced/expanded by the real suites as the build plan progresses. Component subpackages
(activity, focus, model, storage, collector, api) are created per phase, so this test only
checks the top-level package. Build-plan Step 0.2 also asks for a deliberately-failing test
to confirm red shows up; add that locally when running the platform-gate steps rather than
committing a permanently red test.
"""

import timekeeper


def test_package_imports_and_has_version():
    assert timekeeper.__version__ == "0.1.0"
