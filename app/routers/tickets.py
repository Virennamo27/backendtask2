# app/routers/tickets.py
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.collection import Collection
from bson import ObjectId
from typing import Optional, List
from datetime import datetime
from app.dependencies import get_db, get_current_user

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# -----------------------------
# Helper: Convert ObjectId to string (recursive for nested dicts/lists)
# -----------------------------
def serialize_ticket(ticket):
    if not ticket:
        return None

    def serialize(obj):
        if isinstance(obj, dict):
            return {k: serialize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [serialize(i) for i in obj]
        elif isinstance(obj, ObjectId):
            return str(obj)
        else:
            return obj

    return serialize(ticket)

# -----------------------------
# CREATE Ticket
# -----------------------------
@router.post("/")
async def create_ticket(
    data: dict,
    db: Collection = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    users = db["users"]
    tickets = db["tickets"]
    system_state = db["system_state"]

    # Find all agents
    agents = await users.find({"role": "agent"}).to_list(length=1000)  # adjust length as needed
    if not agents:
        raise HTTPException(status_code=400, detail="No agents available")

    # Round-robin logic
    state = await system_state.find_one({"_id": "round_robin"})
    last_agent_index = state.get("last_agent_index", -1) if state else -1
    next_index = (last_agent_index + 1) % len(agents)
    assigned_agent = agents[next_index]

    # Create ticket
    ticket_data = {
        "title": data.get("title"),
        "description": data.get("description"),
        "created_at": datetime.utcnow(),
        "status": "open",
        "created_by": current_user["_id"],
        "assigned_agent_id": assigned_agent["_id"],
        "comments": [],
    }

    result = await tickets.insert_one(ticket_data)

    # Update round-robin state
    system_state.update_one(
        {"_id": "round_robin"},
        {"$set": {"last_agent_index": next_index}},
        upsert=True
    )

    return {"message": "Ticket created", "ticket_id": str(result.inserted_id)}

# -----------------------------
# LIST Tickets
# -----------------------------
@router.get("/")
async def list_tickets(
    db: Collection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    mine: Optional[bool] = Query(False),
    status: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 10
):
    if not current_user or "_id" not in current_user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    tickets_col = db["tickets"]
    query = {}

    # Use get() to safely access role
    role = current_user.get("role", "user")

    if mine:
        if role == "agent":
            query["assigned_agent_id"] = current_user["_id"]
        else:
            query["created_by"] = current_user["_id"]

    if status:
        query["status"] = status

    cursor = tickets_col.find(query).skip(skip).limit(limit)
    tickets_list = [serialize_ticket(t) async for t in cursor]

    return tickets_list

# -----------------------------
# GET Ticket Detail
# -----------------------------
@router.get("/{ticket_id}")
async def get_ticket_detail(
    ticket_id: str,
    db: Collection = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    tickets = db["tickets"]
    users = db["users"]

    ticket = await tickets.find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    agent = await users.find_one({"_id": ticket.get("assigned_agent_id")})
    if agent:
        ticket["assigned_agent_email"] = agent["email"]

    ticket["comments"] = [c for c in ticket.get("comments", []) if c.get("is_public", True)]
    return serialize_ticket(ticket)

# -----------------------------
# UPDATE Ticket Status
# -----------------------------
@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    data: dict,
    db: Collection = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # 1️⃣ Ensure user is authenticated
    if not current_user or "_id" not in current_user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    tickets = db["tickets"]

    # 2️⃣ Fetch the ticket
    ticket = await tickets.find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # 3️⃣ Determine user role safely
    role = current_user.get("role", "user")

    # 4️⃣ Authorization check: admin/agent or ticket creator
    if role not in ["admin", "agent"] and ticket.get("created_by") != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 5️⃣ Prepare updates
    update_fields = {}

    if "status" in data:
        update_fields["status"] = data["status"]

    if "comment" in data:
        comment = {
            "text": data["comment"],
            "created_at": datetime.utcnow(),
            "author_id": current_user["_id"],
            "is_public": data.get("is_public", True)
        }
        await tickets.update_one({"_id": ObjectId(ticket_id)}, {"$push": {"comments": comment}})

    # 6️⃣ Apply status update if present
    if update_fields:
        await tickets.update_one({"_id": ObjectId(ticket_id)}, {"$set": update_fields})

    return {"message": "Ticket updated"}

# -----------------------------
# DELETE Ticket
# -----------------------------
@router.delete("/{ticket_id}")
async def delete_ticket(
    ticket_id: str,
    db: Collection = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # 1️⃣ Ensure user is authenticated
    if not current_user or "_id" not in current_user:
        raise HTTPException(status_code=401, detail="User not authenticated")

    role = current_user.get("role", "user")

    tickets = db["tickets"]

    # 2️⃣ Find the ticket
    ticket = await tickets.find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # 3️⃣ Allow delete only if admin or creator
    if role != "admin" and ticket.get("created_by") != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Admins or ticket owner only")

    # 4️⃣ Delete the ticket
    result = await tickets.delete_one({"_id": ObjectId(ticket_id)})

    return {"message": "Ticket deleted"}

