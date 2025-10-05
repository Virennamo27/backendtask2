# app/routers/tickets.py
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from pydantic import BaseModel

from app.services.assignment import assign_agent_round_robin
from app.dependencies import get_current_user, get_db   # ✅ Correct source

router = APIRouter(prefix="/tickets", tags=["Tickets"])


# -------------------------------
# 📘 Pydantic model for ticket input
# -------------------------------
class TicketCreate(BaseModel):
    title: str
    description: str


# -------------------------------
# 🧰 Utility: Serialize MongoDB documents
# -------------------------------
def serialize_mongo_doc(doc: dict):
    """Convert MongoDB ObjectId to str so FastAPI can return it."""
    if not doc:
        return doc
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc


def serialize_mongo_docs(docs: list[dict]):
    """Convert list of MongoDB docs."""
    return [serialize_mongo_doc(doc) for doc in docs]


# -------------------------------
# 🎯 POST /tickets — create and auto-assign ticket
# -------------------------------
@router.post("/", response_model=dict)
async def create_ticket(
    ticket: TicketCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # 1. Assign agent using round-robin
    agent = await assign_agent_round_robin(db)
    if not agent:
        raise HTTPException(status_code=500, detail="No agents available")

    # 2. Prepare ticket data
    ticket_data = {
        "title": ticket.title,
        "description": ticket.description,
        "created_by": current_user["email"],
        "assigned_to": agent["email"],
        "status": "open"
    }

    # 3. Insert ticket into MongoDB
    result = await db["tickets"].insert_one(ticket_data)
    created_ticket = await db["tickets"].find_one({"_id": result.inserted_id})

    # 4. Return serialized document
    return serialize_mongo_doc(created_ticket)


# -------------------------------
# 📋 GET /tickets — list all tickets
# -------------------------------
@router.get("/", response_model=list[dict])
async def list_tickets(
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    tickets_cursor = db["tickets"].find({})
    tickets = await tickets_cursor.to_list(None)
    return serialize_mongo_docs(tickets)
