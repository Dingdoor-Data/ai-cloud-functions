from pydantic import BaseModel

class UserInfoResponse(BaseModel):
    zipcode: str | None

