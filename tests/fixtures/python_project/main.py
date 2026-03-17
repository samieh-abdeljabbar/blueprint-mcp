from fastapi import FastAPI

from models import User, Post

app = FastAPI()


@app.get("/api/users")
async def list_users():
    return []


@app.post("/api/users")
async def create_user():
    return {"id": 1}


@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id}


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
