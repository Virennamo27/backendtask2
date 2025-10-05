# app/routers/tickets.py
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from pydantic import BaseModel
from datetime import datetime

from app.services.assignment import assign_agent_round_robin
from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# -------------------------------
# Pydantic Models
# -------------------------------
class TicketCreate(BaseModel):
    title: str
    description: str

class CommentCreate(BaseModel):
    text: str

# -------------------------------
# Utilities
# -------------------------------
def serialize_mongo_doc(doc: dict):
    """Convert MongoDB ObjectId to str"""
    if not doc:
        return doc
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc

def serialize_mongo_docs(docs: list[dict]):
    return [serialize_mongo_doc(doc) for doc in docs]

# -------------------------------
# POST /tickets — create ticket
# -------------------------------
@router.post("/", response_model=dict)
async def create_ticket(
    ticket: TicketCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    agent = await assign_agent_round_robin(db)
    if not agent:
        raise HTTPException(status_code=500, detail="No agents available")

    ticket_data = {
        "title": ticket.title,
        "description": ticket.description,
        "created_by": current_user["email"],
        "assigned_to": agent["email"],
        "status": "open",
        "created_at": datetime.utcnow()
    }

    result = await db["tickets"].insert_one(ticket_data)
    created_ticket = await db["tickets"].find_one({"_id": result.inserted_id})
    return serialize_mongo_doc(created_ticket)

# -------------------------------
# GET /tickets — list tickets
# -------------------------------
@router.get("/", response_model=list[dict])
async def list_tickets(
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    tickets_cursor = db["tickets"].find({})
    tickets = await tickets_cursor.to_list(None)
    return serialize_mongo_docs(tickets)

# -------------------------------
# PATCH /tickets/{id} — update ticket
# -------------------------------
@router.patch("/{id}", response_model=dict)
async def update_ticket(
    id: str,
    update_data: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    ticket = await db["tickets"].find_one({"_id": ObjectId(id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.get("status") == "closed":
        raise HTTPException(status_code=400, detail="Cannot update a closed ticket")

    if current_user["email"] not in [ticket["assigned_to"], ticket["created_by"]]:
        raise HTTPException(status_code=403, detail="Not authorized to update this ticket")

    allowed_fields = {"title", "description", "status"}
    updates = {k: v for k, v in update_data.items() if k in allowed_fields}

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    await db["tickets"].update_one({"_id": ObjectId(id)}, {"$set": updates})

    # Audit log for update
    await db["audit_logs"].insert_one({
        "ticket_id": id,
        "action": "update",
        "updated_by": current_user["email"],
        "fields_changed": list(updates.keys()),
        "timestamp": datetime.utcnow()
    })

    updated_ticket = await db["tickets"].find_one({"_id": ObjectId(id)})
    return serialize_mongo_doc(updated_ticket)

# -------------------------------
# POST /tickets/{id}/comment — add public comment
# -------------------------------
@router.post("/{id}/comment", response_model=dict)
async def add_comment(
    id: str,
    comment: CommentCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    ticket = await db["tickets"].find_one({"_id": ObjectId(id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    comment_data = {
        "ticket_id": id,
        "author": current_user["email"],
        "text": comment.text,
        "is_public": True,
        "created_at": datetime.utcnow()
    }

    result = await db["comments"].insert_one(comment_data)

    # Audit log for comment
    await db["audit_logs"].insert_one({
        "ticket_id": id,
        "action": "comment",
        "author": current_user["email"],
        "comment_id": str(result.inserted_id),
        "timestamp": datetime.utcnow()
    })

    return {**comment_data, "_id": str(result.inserted_id)}

# -------------------------------
# GET /tickets/{id}/comments — list comments
# -------------------------------
@router.get("/{id}/comments", response_model=list[dict])
async def get_comments(
    id: str,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    comments_cursor = db["comments"].find({"ticket_id": id})
    comments = await comments_cursor.to_list(None)
    for c in comments:
        c["_id"] = str(c["_id"])
    return comments
