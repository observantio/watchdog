from pydantic import BaseModel

class OtlpValidateRequest(BaseModel):
    token: str | None = None