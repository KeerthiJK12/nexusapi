from pydantic import BaseModel, Field


class SummariseRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)


class SummariseResponse(BaseModel):
    job_id: str
    status: str
