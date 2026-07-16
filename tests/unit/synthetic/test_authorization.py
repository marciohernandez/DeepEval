"""Unit tests for AuthenticatedPrincipal/OrganizationAuthorizer (M4.1, T011).

Supabase Auth is mocked at the create_client boundary; no network calls are made.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from deepeval_platform.synthetic.authorization import (
    AuthenticatedPrincipal,
    AuthorizationError,
    OrganizationAuthorizer,
)

_VALID_USER_ID = "11111111-1111-1111-1111-111111111111"
_VALID_ORG_ID = "22222222-2222-2222-2222-222222222222"


def _config(url="https://test.supabase.co", anon_key="anon-test-key"):
    config = MagicMock()
    values = {"SUPABASE_URL": url, "SUPABASE_ANON_KEY": anon_key}
    config.get.side_effect = lambda key: values[key]
    return config


def _user_response(user_id=_VALID_USER_ID, org_id=_VALID_ORG_ID):
    user = MagicMock()
    user.id = user_id
    user.app_metadata = {"org_id": org_id} if org_id is not None else {}
    response = MagicMock()
    response.user = user
    return response


class TestAuthorizeSuccess:
    def test_valid_jwt_resolves_principal(self, mocker):
        client = MagicMock()
        client.auth.get_user.return_value = _user_response()
        create_client = mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        principal = authorizer.authorize("valid-access-token")

        assert isinstance(principal, AuthenticatedPrincipal)
        assert principal.user_id == UUID(_VALID_USER_ID)
        assert principal.org_id == UUID(_VALID_ORG_ID)
        assert principal.access_token == "valid-access-token"
        assert principal.supabase_client is client
        create_client.assert_called_once_with("https://test.supabase.co", "anon-test-key")

    def test_client_is_scoped_with_user_jwt(self, mocker):
        client = MagicMock()
        client.auth.get_user.return_value = _user_response()
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        authorizer.authorize("valid-access-token")

        client.postgrest.auth.assert_called_once_with("valid-access-token")


class TestAuthorizeFailure:
    def test_invalid_token_raises(self, mocker):
        client = MagicMock()
        client.auth.get_user.side_effect = Exception("invalid token")
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("bad-token")

    def test_expired_token_raises(self, mocker):
        client = MagicMock()
        client.auth.get_user.side_effect = Exception("token is expired")
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("expired-token")

    def test_missing_user_raises(self, mocker):
        client = MagicMock()
        response = MagicMock()
        response.user = None
        client.auth.get_user.return_value = response
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("no-user-token")

    def test_missing_org_id_raises(self, mocker):
        client = MagicMock()
        client.auth.get_user.return_value = _user_response(org_id=None)
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("no-org-token")

    def test_malformed_org_id_raises(self, mocker):
        client = MagicMock()
        client.auth.get_user.return_value = _user_response(org_id="not-a-uuid")
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("malformed-org-token")

    def test_client_setup_failure_raises(self, mocker):
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            side_effect=Exception("cannot connect"),
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("any-token")


class TestNoOrgOverride:
    def test_authorize_accepts_only_access_token(self):
        signature = inspect.signature(OrganizationAuthorizer.authorize)
        params = [p for p in signature.parameters if p != "self"]
        assert params == ["access_token"]


class TestTokenSecrecy:
    def test_principal_repr_does_not_expose_access_token(self, mocker):
        client = MagicMock()
        client.auth.get_user.return_value = _user_response()
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        principal = authorizer.authorize("super-secret-access-token")

        assert "super-secret-access-token" not in repr(principal)
        assert "super-secret-access-token" not in str(principal)


class TestCoverageGaps:
    """Closes coverage gaps identified by T043 for authorization.py."""

    def test_non_uuid_user_id_raises(self, mocker):
        client = MagicMock()
        client.auth.get_user.return_value = _user_response(user_id="not-a-uuid")
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("bad-user-id-token")

    def test_postgrest_scoping_failure_raises(self, mocker):
        client = MagicMock()
        client.auth.get_user.return_value = _user_response()
        client.postgrest.auth.side_effect = Exception("cannot scope client")
        mocker.patch(
            "deepeval_platform.synthetic.authorization.create_client",
            return_value=client,
        )

        authorizer = OrganizationAuthorizer(config=_config())
        with pytest.raises(AuthorizationError):
            authorizer.authorize("valid-access-token")
