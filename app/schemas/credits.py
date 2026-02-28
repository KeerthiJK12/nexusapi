from pydantic import BaseModel, Field


class GrantCreditsRequest(BaseModel):
    amount: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=255)
    user_id: str | None = None


class BalanceResponse(BaseModel):
    balance: int


class CreditTransactionResponse(BaseModel):
    id: str
    amount: int
    reason: str
    created_at: str | None = None


class BalanceWithTransactionsResponse(BaseModel):
    balance: int
    transactions: list[CreditTransactionResponse]
