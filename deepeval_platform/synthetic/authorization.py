"""OrganizationAuthorizer — validates Supabase Auth JWTs and derives a trusted
AuthenticatedPrincipal, never accepting a caller-supplied org_id (M4.1, R7).
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from supabase import Client, create_client

from deepeval_platform.config.config_manager import ConfigManager


class AuthorizationError(Exception):
    pass


@dataclass
class AuthenticatedPrincipal:
    user_id: UUID
    org_id: UUID
    access_token: str
    supabase_client: Client

    def __repr__(self) -> str:
        return (
            f"AuthenticatedPrincipal(user_id={self.user_id!r}, org_id={self.org_id!r}, "
            f"access_token=***, supabase_client={self.supabase_client!r})"
        )


class OrganizationAuthorizer:
    def __init__(self, config: ConfigManager | None = None) -> None:
        self._config = config if config is not None else ConfigManager.instance()

    def authorize(self, access_token: str) -> AuthenticatedPrincipal:
        url = self._config.get("SUPABASE_URL")
        anon_key = self._config.get("SUPABASE_ANON_KEY")

        try:
            client = create_client(url, anon_key)
            response = client.auth.get_user(access_token)
        except Exception as exc:
            raise AuthorizationError("Invalid or expired access token") from exc

        user = getattr(response, "user", None)
        if user is None:
            raise AuthorizationError("Access token did not resolve to a user")

        try:
            user_id = UUID(str(user.id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise AuthorizationError("Access token has no valid user id") from exc

        app_metadata = getattr(user, "app_metadata", None) or {}
        raw_org_id = app_metadata.get("org_id")
        if not raw_org_id:
            raise AuthorizationError("Trusted app_metadata.org_id is missing")

        try:
            org_id = UUID(str(raw_org_id))
        except (ValueError, TypeError):
            raise AuthorizationError("Trusted app_metadata.org_id is malformed")

        try:
            client.postgrest.auth(access_token)
        except Exception as exc:
            raise AuthorizationError("Could not scope Supabase client to user JWT") from exc

        return AuthenticatedPrincipal(
            user_id=user_id,
            org_id=org_id,
            access_token=access_token,
            supabase_client=client,
        )
