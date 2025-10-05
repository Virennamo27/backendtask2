from pydantic import BaseModel
from typing import Optional

class TicketCreate(BaseModel):
    title: str
    description: str
    priority: Optional[str] = "normal"  # default priority
    created_by: str  # user email or id
