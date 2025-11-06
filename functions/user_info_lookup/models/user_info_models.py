from pydantic import BaseModel

class UserInfoResponse(BaseModel):
    zipCode: str | None

