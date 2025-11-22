#!/usr/bin/env python3
"""
Create Demo User Script

Creates a demo user for testing purposes.
Credentials: demo@example.com / Demo1234
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import argon2
import os

async def create_demo_user():
    # Get MongoDB connection from environment
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
    db_name = os.getenv("MONGODB_DB_NAME", "octavios_chat")

    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]

    # Demo user credentials
    email = "demo@example.com"
    password = "Demo1234"
    hashed_password = argon2.hash(password)

    # Check if user already exists
    existing_user = await db.users.find_one({"email": email})

    if existing_user:
        print(f"✅ Demo user already exists: {email}")
        print(f"   Use password: {password}")
        return

    # Create demo user
    user_doc = {
        "email": email,
        "hashed_password": hashed_password,
        "is_active": True,
        "is_superuser": False,
    }

    result = await db.users.insert_one(user_doc)

    print(f"✅ Demo user created successfully!")
    print(f"   Email: {email}")
    print(f"   Password: {password}")
    print(f"   User ID: {result.inserted_id}")

if __name__ == "__main__":
    asyncio.run(create_demo_user())
