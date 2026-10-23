"""Content-addressed evidence references."""

from pydantic import BaseModel, ConfigDict, Field


class ArtifactRef(BaseModel):
    """Content-addressed bytes in the run's artifact store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    uri: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
