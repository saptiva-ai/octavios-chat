#!/usr/bin/env python3
"""
Debug script to inspect the last chat message's Saptiva response structure.
This will help diagnose why content is empty in the response.
"""

from pymongo import MongoClient

MONGO_URI = "mongodb://octavios_user:octavios_password_change_me@localhost:27018/octavios?authSource=admin"

def main():
    print("=" * 80)
    print("SAPTIVA RESPONSE STRUCTURE DEBUG")
    print("=" * 80)
    print()

    # Connect to MongoDB
    client = MongoClient(MONGO_URI)
    db = client.octavios

    # Get the last chat message (assistant)
    last_message = db.chat_messages.find_one(
        {"role": "assistant"},
        sort=[("created_at", -1)]
    )

    if not last_message:
        print("❌ No assistant messages found")
        return

    print("LAST ASSISTANT MESSAGE:")
    print("-" * 80)
    print(f"ID: {last_message['_id']}")
    print(f"Chat ID: {last_message.get('chat_id')}")
    print(f"Created: {last_message.get('created_at')}")
    print(f"Role: {last_message.get('role')}")
    print()

    content = last_message.get("content", "")
    print(f"Content length: {len(content)}")
    print(f"Content preview: {content[:200] if content else '(EMPTY)'}")
    print()

    # Check metadata for Saptiva response
    metadata = last_message.get("metadata", {})
    print("METADATA:")
    print("-" * 80)
    for key, value in metadata.items():
        print(f"{key}: {value}")
    print()

    # Get the corresponding chat session
    chat_id = last_message.get("chat_id")
    if chat_id:
        session = db.chat_sessions.find_one({"_id": chat_id})
        if session:
            print("SESSION INFO:")
            print("-" * 80)
            print(f"Title: {session.get('title')}")
            print(f"Model: {session.get('settings', {}).get('model')}")
            print(f"Attached files: {session.get('attached_file_ids', [])}")
            print()

    # Get the user message before this
    user_message = db.chat_messages.find_one(
        {
            "chat_id": chat_id,
            "role": "user",
            "created_at": {"$lt": last_message.get("created_at")}
        },
        sort=[("created_at", -1)]
    )

    if user_message:
        print("USER MESSAGE (CONTEXT):")
        print("-" * 80)
        print(f"Content: {user_message.get('content')}")
        print(f"File IDs: {user_message.get('file_ids', [])}")
        print()

    client.close()

    # Diagnosis
    print("=" * 80)
    print("DIAGNOSIS:")
    print("=" * 80)
    if not content or len(content) == 0:
        print("❌ PROBLEM: Assistant message content is EMPTY")
        print("   This confirms the bug - Saptiva responded but content wasn't saved")
        print()
        print("   Possible causes:")
        print("   1. chat_strategy.py:212-217 - response_obj extraction logic")
        print("   2. SaptivaResponse.choices format mismatch")
        print("   3. response_content variable is empty before sanitization")
    else:
        print("✅ Content exists - no issue detected")
        print(f"   Content length: {len(content)} chars")

if __name__ == "__main__":
    main()
