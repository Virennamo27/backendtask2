from pydantic import BaseModel, Field

class TicketCreate(BaseModel):
    title: str = Field(..., min_length=3)
    description: str

class TicketInDB(TicketCreate):
    id: str
    status: str
    assigned_agent_email: str