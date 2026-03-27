from typing import List

from pydantic import BaseModel, field_validator


class AnalyzeRequest(BaseModel):
    tickers: List[str]

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, values: List[str]) -> List[str]:
        cleaned = [v.strip().upper() for v in values if v and v.strip()]
        unique = list(dict.fromkeys(cleaned))
        if len(unique) < 7:
            raise ValueError("Please provide at least 7 unique ticker symbols")
        return unique
