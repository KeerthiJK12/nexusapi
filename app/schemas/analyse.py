from pydantic import BaseModel, Field


class AnalyseRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class AnalyseResponse(BaseModel):
    result: str
    credits_remaining: int
