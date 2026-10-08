import pytest
from scripts.verify_ci_identity import (
    IdentityVerificationError,
    verify_identity,
)


def test_accepts_expected_service_principal_application_id():
    verify_identity(
        {"applicationId": "deployer-id", "displayName": "retail-deployer"},
        "deployer-id",
    )


def test_accepts_scim_username_shape_for_service_principal():
    verify_identity({"userName": "deployer-id"}, "deployer-id")


def test_rejects_personal_or_unexpected_identity():
    with pytest.raises(IdentityVerificationError, match="does not match"):
        verify_identity({"userName": "engineer@example.com"}, "deployer-id")


def test_rejects_non_object_output():
    with pytest.raises(IdentityVerificationError, match="must be an object"):
        verify_identity([], "deployer-id")
