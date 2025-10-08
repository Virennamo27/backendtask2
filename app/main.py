# app/main.py
print("✅ main.py loaded")  # Debug: confirm this file is running

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from app import auth
from app.auth import get_password_hash, verify_password, create_access_token
from app.db import db
from app.routers import tickets  # Tickets router

# -------------------------
# Initialize FastAPI App
# -------------------------
app = FastAPI(title="Ticketing System API")

# -------------------------
# Root Route
# -------------------------
@app.get("/")
def read_root():
    return {"message": "Welcome to the Ticketing System API!"}

# -------------------------
# Include Routers
# -------------------------
app.include_router(tickets.router)

# -------------------------
# OAuth2 Configuration
# -------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

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
# Auth Dependency
# -------------------------
async def get_current_user(token: str = Depends(oauth2_scheme)):
    from app.auth import SECRET_KEY, ALGORITHM
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        user = await db["users"].find_one({"email": email})
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        user["_id"] = str(user["_id"])
        return user
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# -------------------------
# Protected Route Example
# -------------------------
@app.get("/users/me")
async def read_me(current_user: dict = Depends(get_current_user)):
    return current_user

# -------------------------
# Public Route Example
# -------------------------
@app.get("/users")
async def get_users():
    users = []
    cursor = db["users"].find({})
    async for user in cursor:
        user["_id"] = str(user["_id"])
        users.append(user)
    return users
