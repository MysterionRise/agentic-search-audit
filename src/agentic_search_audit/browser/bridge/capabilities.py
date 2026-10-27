"""Capability constants for the bridge transports."""

from ...core.types import BrowserCapabilities, get_capabilities

__all__ = [
    "BrowserCapabilities",
    "LAUNCH_CAPABILITIES",
    "REAL_PROFILE_CAPABILITIES",
    "get_capabilities",
    "real_profile_capabilities",
]

#: A bridge attached to the user's real, logged-in profile: identity mutations are off.
REAL_PROFILE_CAPABILITIES = BrowserCapabilities(
    user_agent_override=False,
    proxy=False,
    clear_cookies=False,
    isolated_profile=False,
    trusted_click=False,
    snapshot=True,
)

#: A bridge that launched its own disposable Chrome.
LAUNCH_CAPABILITIES = BrowserCapabilities(trusted_click=False, snapshot=True)


def real_profile_capabilities(
    *, allow_profile_mutations: bool = False, trusted_click: bool = False
) -> BrowserCapabilities:
    """Real-profile capabilities, optionally with UA override and cookie clearing enabled."""
    return REAL_PROFILE_CAPABILITIES.model_copy(
        update={
            "user_agent_override": allow_profile_mutations,
            "clear_cookies": allow_profile_mutations,
            "trusted_click": trusted_click,
        }
    )
