#!/usr/bin/env python3
"""
Test Saptiva Streaming - Diagnose streaming connection issues
"""
import asyncio
import httpx
import os

async def test_saptiva_streaming():
    """Test Saptiva API streaming endpoint"""

    api_key = os.getenv("SAPTIVA_API_KEY", "")
    base_url = os.getenv("SAPTIVA_BASE_URL", "https://api.saptiva.com")

    print(f"🔑 API Key: {api_key[:20]}...{api_key[-10:]}")
    print(f"🌐 Base URL: {base_url}")
    print()

    url = f"{base_url.rstrip('/')}/v1/chat/completions/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "Saptiva Turbo",
        "messages": [
            {"role": "user", "content": "Say hello"}
        ],
        "max_tokens": 50,
        "stream": True  # Enable streaming
    }

    print("📡 Testing Saptiva STREAMING endpoint...")
    print(f"   URL: {url}")
    print(f"   Stream: True")
    print()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                print(f"📊 Response Status: {response.status_code}")
                print(f"📋 Response Headers:")
                for key, value in response.headers.items():
                    if key.lower() in ['content-type', 'x-request-id', 'server', 'transfer-encoding']:
                        print(f"   {key}: {value}")
                print()

                if response.status_code != 200:
                    error_body = await response.aread()
                    print(f"❌ Streaming failed: {response.status_code}")
                    print(f"📄 Error: {error_body.decode('utf-8')}")
                    return False

                print("✅ Streaming connection established!")
                print("📝 Streaming chunks:")
                print("-" * 60)

                chunk_count = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            print("\n✅ Stream completed with [DONE]")
                            break
                        chunk_count += 1
                        print(f"Chunk {chunk_count}: {data[:80]}")

                print("-" * 60)
                print(f"✅ Received {chunk_count} chunks successfully")
                return True

    except httpx.RemoteProtocolError as e:
        print(f"❌ RemoteProtocolError (HTTP/2 issue): {e}")
        print("   This usually means the server closed the connection unexpectedly")
        print("   Possible causes:")
        print("   - Server doesn't support HTTP/2 streaming properly")
        print("   - Firewall/proxy interfering with connection")
        print("   - Server-side timeout or bug")
        return False
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_saptiva_streaming())
    exit(0 if result else 1)
