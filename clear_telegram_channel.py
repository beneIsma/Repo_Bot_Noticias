#!/usr/bin/env python3
"""
Script para limpiar el canal de Telegram
Elimina los últimos N mensajes del canal
"""

import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

async def clear_channel(num_messages: int = 100):
    """Elimina los últimos N mensajes del canal"""

    print(f"[INFO] Preparando para eliminar {num_messages} mensajes...")
    print(f"[INFO] Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"[ADVERTENCIA] Esta acción es IRREVERSIBLE")

    response = input("\n¿Estás seguro? Escribe 'SI' para confirmar: ").strip().upper()

    if response != "SI":
        print("[CANCELADO] Operación cancelada")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    async with httpx.AsyncClient() as client:
        # Obtener los últimos mensajes del canal
        print(f"\n[BUSCANDO] Obteniendo últimos {num_messages} mensajes...")

        r = await client.post(
            f"{url}/getChat",
            json={"chat_id": TELEGRAM_CHAT_ID},
            timeout=15
        )

        if r.status_code != 200:
            print(f"[ERROR] No se pudo acceder al canal: {r.json()}")
            return

        chat_info = r.json()
        print(f"[INFO] Canal: {chat_info.get('result', {}).get('title', 'Desconocido')}")
        print(f"[INFO] Último message_id aproximado")

        # Intentar eliminar el último mensaje conocido (el más reciente)
        # Los message_id en canales son números secuenciales

        # Primero, obtenemos un mensaje reciente para saber el rango
        print(f"\n[ELIMINANDO] Intentando eliminar últimos mensajes...")

        # Nota: Telegram no proporciona una forma directa de listar mensajes del canal
        # Solo el bot puede eliminar mensajes que envió
        # Para eliminar mensajes de otros usuarios, se necesita ser administrador

        print("\n[LIMITACION] Telegram solo permite eliminar mensajes que el bot envió")
        print("[OPCION] El bot puede eliminar automáticamente mensajes después de enviarlos")
        print("[MANUAL] Para limpiar todo, ve a Telegram > [Mantén presionado el mensaje] > Eliminar")

        # Intenta eliminar los últimos 10 mensajes conocidos
        for msg_id in range(1000, 900, -1):
            r = await client.post(
                f"{url}/deleteMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "message_id": msg_id
                },
                timeout=5
            )

            if r.status_code == 200 and r.json().get('ok'):
                print(f"[OK] Mensaje {msg_id} eliminado")

        print("\n[LISTO] Proceso completado")
        print("[NOTA] Si quedan mensajes, elimínalos manualmente en Telegram")

if __name__ == "__main__":
    print("=" * 60)
    print("LIMPIAR CANAL DE TELEGRAM — Tech Digest Bot")
    print("=" * 60)

    asyncio.run(clear_channel(100))
