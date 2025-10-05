# app/routers/tickets.py
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from pydantic import BaseModel
from app.services.assignment import assign_agent_round_robin
from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# -------------------------------
# Pydantic model for ticket input
# -------------------------------
class TicketCreate(BaseModel):
    title: str
    description: str

# -------------------------------
# Utility: Serialize MongoDB documents
# -------------------------------
def serialize_mongo_doc(doc: dict):
    """Convert MongoDB ObjectId to str so FastAPI can return it."""
    if not doc:
        return doc
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    # Also convert referenced ObjectIds (ticket_id in comments) if present
    if "ticket_id" in doc and isinstance(doc["ticket_id"], ObjectId):
        doc["ticket_id"] = str(doc["ticket_id"])
    return doc

def serialize_mongo_docs(docs: list[dict]):
    """Convert list of MongoDB docs."""
    return [serialize_mongo_doc(doc) for doc in docs]

# -------------------------------
# POST /tickets — create and auto-assign ticket
# -------------------------------
@router.post("/", response_model=dict)
async def create_ticket(
    ticket: TicketCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
        "priority": "normal",
        "created_at": __import__("datetime").datetime.utcnow(),
    }

    result = await db["tickets"].insert_one(ticket_data)
    created_ticket = await db["tickets"].find_one({"_id": result.inserted_id})
    return serialize_mongo_doc(created_ticket)

# -------------------------------
# GET /tickets — list tickets (filters + pagination)
# -------------------------------
@router.get("/", response_model=dict)
async def list_tickets(
    mine: bool = Query(True, description="If true, show only tickets created by or assigned to current user"),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Quick search on title/description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Build query conditions
    conditions = []
    if mine:
        conditions.append({"$or": [{"created_by": current_user["email"]}, {"assigned_to": current_user["email"]}]})
    if status:
        conditions.append({"status": status})
    if priority:
        conditions.append({"priority": priority})
    if q:
        regex = {"$regex": q, "$options": "i"}
        conditions.append({"$or": [{"title": regex}, {"description": regex}]})

    query = {"$and": conditions} if conditions else {}

    # Pagination
    skip = (page - 1) * page_size

    total = await db["tickets"].count_documents(query)
    cursor = db["tickets"].find(query).sort("created_at", -1).skip(skip).limit(page_size)
    items = await cursor.to_list(length=page_size)
    items = serialize_mongo_docs(items)

    return {"items": items, "total": total, "page": page, "page_size": page_size}

# -------------------------------
# GET /tickets/{ticket_id} — ticket detail + assigned agent + latest public comments
# -------------------------------
@router.get("/{ticket_id}", response_model=dict)
async def get_ticket_detail(
    ticket_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        oid = ObjectId(ticket_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ticket id")

    ticket = await db["tickets"].find_one({"_id": oid})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Fetch assigned agent metadata
    assigned_email = ticket.get("assigned_to")
    agent_info = None
    if assigned_email:
        agent = await db["agents"].find_one({"email": assigned_email})
        if agent:
            agent_info = {"email": agent.get("email"), "name": agent.get("name")}
        else:
            agent_info = {"email": assigned_email}

    # Fetch recent public comments
    comments = []
    try:
        comments_cursor = db["comments"].find({"ticket_id": oid, "is_public": True}).sort("created_at", -1).limit(5)
        comments = await comments_cursor.to_list(length=5)
        comments = serialize_mongo_docs(comments)
    except Exception:
        comments = []

    ticket = serialize_mongo_doc(ticket)
    ticket["assigned_agent"] = agent_info
    ticket["latest_public_comments"] = comments
    return ticket

# -------------------------------
# PATCH /tickets/{ticket_id} – update ticket status
# -------------------------------
@router.patch("/{ticket_id}", response_model=dict)
async def update_ticket_status(
    ticket_id: str,
    status_update: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update the status of a ticket (open, in_progress, closed).
    Only admins or the ticket owner can change status.
    """
    try:
        oid = ObjectId(ticket_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ticket id")

    ticket = await db["tickets"].find_one({"_id": oid})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Authorization check
    if (
        current_user.get("role") != "admin"
        and ticket.get("created_by") != current_user["email"]
    ):
        raise HTTPException(status_code=403, detail="Not authorized to update this ticket")

    new_status = status_update.get("status")
    if new_status not in ["open", "in_progress", "closed"]:
        raise HTTPException(status_code=400, detail="Invalid status value")

    await db["tickets"].update_one({"_id": oid}, {"$set": {"status": new_status}})
    updated = await db["tickets"].find_one({"_id": oid})
    return serialize_mongo_doc(updated)

# -------------------------------
# DELETE /tickets/{ticket_id} – delete ticket (admin only)
# -------------------------------
@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Allow only admin users to delete tickets."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only can delete tickets")

    try:
        oid = ObjectId(ticket_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ticket id")

    result = await db["tickets"].delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return None
