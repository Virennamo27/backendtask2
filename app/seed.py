from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

MONGO_URL = "mongodb+srv://viren_be1:12345@cluster1.7toykvn.mongodb.net/helpdesk?retryWrites=true&w=majority"
client = AsyncIOMotorClient(MONGO_URL)
db = client["support_db"]

async def seed():
    tickets = [
        {"title": "Dummy Ticket 1", "description": "Test issue", "status": "open", "assigned_to": "agent1@example.com"},
        {"title": "Dummy Ticket 2", "description": "Another issue", "status": "open", "assigned_to": "agent2@example.com"}
    ]
    await db.tickets.insert_many(tickets)
    print("Dummy tickets inserted!")

asyncio.run(seed())
