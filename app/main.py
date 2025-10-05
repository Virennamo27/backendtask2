# app/main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from datetime import datetime

from app.auth import get_password_hash, verify_password, create_access_token
from app.db import db
from app.routers import tickets
from app.dependencies import get_current_user

app = FastAPI(title="Ticketing System API")

# Include tickets router
app.include_router(tickets.router)

# -------------------------
# Pydantic Models
# -------------------------
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

# -------------------------
# Signup Route
# -------------------------
@app.post("/auth/signup", status_code=201)
async def signup(user: UserCreate):
    existing_user = await db["users"].find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_dict = user.dict()
    user_dict["password"] = get_password_hash(user_dict["password"])
    user_dict["created_at"] = datetime.utcnow()
    result = await db["users"].insert_one(user_dict)
    return {"id": str(result.inserted_id), "email": user.email}

# -------------------------
# Login Route
# -------------------------
@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db["users"].find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    access_token = create_access_token({"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

# -------------------------
# Protected route example
# -------------------------
@app.get("/users/me")
async def read_me(current_user: dict = Depends(get_current_user)):
    return current_user

# -------------------------
# Public route
# -------------------------
@app.get("/users")
async def get_users():
    users = []
    cursor = db["users"].find({})
    async for user in cursor:
        user["_id"] = str(user["_id"])
        users.append(user)
    return users
