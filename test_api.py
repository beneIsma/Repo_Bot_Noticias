#!/usr/bin/env python3
"""Test simple de la API de Anthropic"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('ANTHROPIC_API_KEY')

print(f"[TEST] API Key: {api_key[:30]}...")
print(f"[TEST] Longitud: {len(api_key)}")

# Test simple
data = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 100,
    "messages": [
        {"role": "user", "content": "Hola, ¿quién eres?"}
    ]
}

print("\n[TEST] Enviando solicitud a Anthropic...")
print(f"[TEST] Datos: {data}")

with httpx.Client() as client:
    r = client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=data,
        timeout=10
    )

    print(f"\n[RESPUESTA] Status: {r.status_code}")
    print(f"[RESPUESTA] Headers: {dict(r.headers)}")
    print(f"[RESPUESTA] Body: {r.text[:500]}")

    if r.status_code == 200:
        print("\n✅ API funciona correctamente")
    else:
        print(f"\n❌ Error: {r.status_code}")
