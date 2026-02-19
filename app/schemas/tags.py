from pydantic import BaseModel
from typing import List

class TagsResponse(BaseModel):
    success: bool
    tags: List[str]
    extraTags: List[str]
