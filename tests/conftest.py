"""Shared fixtures for the test suite."""

from __future__ import annotations

import pytest

from pixgen.core.models import MediaRoleSpec, ModelSpec  # noqa: TC001
from tests.factories import make_media_role_spec, make_model_spec


@pytest.fixture
def model_spec() -> ModelSpec:
    """Provide a default test model specification."""
    return make_model_spec()


@pytest.fixture
def media_role_spec() -> MediaRoleSpec:
    """Provide a default test media role specification."""
    return make_media_role_spec()
