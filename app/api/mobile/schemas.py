"""Mobile API — Shared Pydantic response schemas."""

from pydantic import BaseModel


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int
