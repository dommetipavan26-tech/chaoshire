"""Pydantic request models for the public API."""
from pydantic import BaseModel, Field


class AppealRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=5000)


class MitigationRequest(BaseModel):
    strategies: list[str]


class UploadRequest(BaseModel):
    csv: str = Field(min_length=1, max_length=5_000_000)
