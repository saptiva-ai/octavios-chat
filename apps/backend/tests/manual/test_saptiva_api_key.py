#!/usr/bin/env python3
"""
Test Saptiva API Key - Minimal test to verify API connectivity
"""
import asyncio
import httpx
import os

async def test_saptiva_api_key():
    """Test Saptiva API with minimal request"""

    api_key = os.getenv("SAPTIVA_API_KEY", "")
    base_url = os.getenv("SAPTIVA_BASE_URL", "https://api.saptiva.com")

    if not api_key:
        print("❌ SAPTIVA_API_KEY not found in environment")
        return False

    print(f"🔑 API Key: {api_key[:20]}...{api_key[-10:]}")
    print(f"🌐 Base URL: {base_url}")
    print()

    # Minimal test request
    url = f"{base_url.rstrip('/')}/v1/chat/completions/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "Saptiva Turbo",
        "messages": [
            {"role": "user", "content": "Test"}
        ],
        "max_tokens": 10,
        "stream": False  # Non-streaming for simplicity
    }

    print("📡 Testing Saptiva API with minimal request...")
    print(f"   URL: {url}")
    print(f"   Model: Saptiva Turbo")
    print(f"   Stream: False")
    print()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            print(f"📊 Response Status: {response.status_code}")
            print(f"📋 Response Headers:")
            for key, value in response.headers.items():
                if key.lower() in ['content-type', 'x-request-id', 'server']:
                    print(f"   {key}: {value}")
            print()

            if response.status_code == 200:
                print("✅ API Key is VALID and working!")
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    content = data['choices'][0].get('message', {}).get('content', '')
                    print(f"📝 Sample response: {content[:100]}")
                return True
            else:
                print(f"❌ API returned error: {response.status_code}")
                print(f"📄 Response body:")
                try:
                    error_data = response.json()
                    import json
                    print(json.dumps(error_data, indent=2))
                except:
                    print(response.text[:500])
                return False

    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e}")
        print(f"   Response: {e.response.text[:500]}")
        return False
    except httpx.RequestError as e:
        print(f"❌ Request Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected Error: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_saptiva_api_key())
    exit(0 if result else 1)
