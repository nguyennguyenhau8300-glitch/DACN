from typing import ClassVar
from pydantic import BaseModel, field_validator

class InputModel(BaseModel):
    # Omitted PATCH fields remain optional; explicit null for required DB columns is invalid.
    non_nullable: ClassVar[set[str]] = set()
    model_config = {'str_strip_whitespace': True}

    @field_validator('*', mode='before')
    @classmethod
    def reject_null(cls, value, info):
        if value is None and info.field_name in cls.non_nullable:
            raise ValueError('Trường bắt buộc không được null')
        return value
