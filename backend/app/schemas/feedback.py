from typing import Literal

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    message: str = Field(..., max_length=2000)
    feedback_type: Literal["up", "down"]
