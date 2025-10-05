# app/services/assignment.py
from motor.motor_asyncio import AsyncIOMotorDatabase

async def assign_agent_round_robin(db: AsyncIOMotorDatabase):
    agents = await db.agents.find({"is_active": True}).to_list(length=None)
    if not agents:
        return None

    state = await db.system_state.find_one({}) or {}
    last_index = state.get("last_assigned_index", -1)

    next_index = (last_index + 1) % len(agents)
    next_agent = agents[next_index]

    await db.system_state.update_one(
        {}, {"$set": {"last_assigned_index": next_index}}, upsert=True
    )

    return next_agent
