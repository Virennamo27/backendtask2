# app/seed_sample_agents.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
client = AsyncIOMotorClient(MONGO_URI)
db = client["helpdesk"]  # Make sure this matches your DB name in main.py

async def seed_agents():
    agents = [
        {"name": "Agent A", "email": "agentA@example.com", "is_active": True, "assigned_tickets": []},
        {"name": "Agent B", "email": "agentB@example.com", "is_active": True, "assigned_tickets": []},
        {"name": "Agent C", "email": "agentC@example.com", "is_active": True, "assigned_tickets": []}
    ]

    await db.agents.delete_many({})  # optional: clear existing agents
    await db.agents.insert_many(agents)
    print("✅ Seeded sample agents successfully!")

if __name__ == "__main__":
    asyncio.run(seed_agents())