#!/usr/bin/env python3
"""Test de Telegram API"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')

print(f"[TEST] Bot Token: {bot_token[:30]}...")
print(f"[TEST] Chat ID: {chat_id}")

# Test 1: Verificar que el bot existe
print("\n[TEST 1] Verificando bot...")
with httpx.Client() as client:
    r = client.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")

# Test 2: Enviar mensaje simple
print("\n[TEST 2] Enviando mensaje de prueba...")
with httpx.Client() as client:
    payload = {
        "chat_id": chat_id,
        "text": "Prueba del bot - Tech Digest v2.5",
        "parse_mode": "HTML"
    }
    r = client.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json=payload,
        timeout=10
    )
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")

print("\n[DONE]")
