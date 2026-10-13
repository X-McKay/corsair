"""The identification toolsets offer exactly their registered tools; any change to what they offer changes the digest."""

from corsair.agents.issue_identification.tools import (
    REPOSITORY_TOOLSET_SHA256, TOOLSET_SHA256, identification_tools, repository_tools,
)
from corsair.agents.toolset_identity import toolset_sha256

# Recorded from the pre-split issue_analysis modules (SPEC-0052); change only with a reviewed tool change.
OFFERED_SHA256 = "de138f51be4438ac79d0ffd719eca5f5c58c6ee27d873e69cfb3180b43398c61"
REPOSITORY_OFFERED_SHA256 = "67947c2de4fa22fcb9adb54ae3e1210a707de21120a2dd792de63b645128e2c1"


def test_toolsets_offer_exactly_the_registered_tools():
    inline, repository = identification_tools(), repository_tools()
    assert (inline.id, list(inline.tools)) == ("issue_identification_source", ["read_source"])
    assert repository.wrapped.id == "issue_identification_repository_source"
    assert list(repository.wrapped.tools) == ["list_source", "search_source", "read_source"]


def test_toolset_digests_are_unchanged_by_the_package_split():
    assert TOOLSET_SHA256 == toolset_sha256(identification_tools()) == OFFERED_SHA256
    assert REPOSITORY_TOOLSET_SHA256 == toolset_sha256(repository_tools()) == REPOSITORY_OFFERED_SHA256
