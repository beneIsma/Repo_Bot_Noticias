#!/usr/bin/env python3
"""
Bot de comandos para Telegram — Escucha /limpiar para limpiar el canal
Ejecuta este script continuamente para que funcione
"""

import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

class TelegramCommandHandler:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.last_update_id = 0

    async def get_updates(self):
        """Obtiene nuevos mensajes del canal"""
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{self.api_url}/getUpdates",
                    json={"offset": self.last_update_id + 1, "timeout": 30},
                    timeout=35
                )

                if r.status_code != 200:
                    return []

                data = r.json()
                if not data.get('ok'):
                    return []

                updates = data.get('result', [])
                if updates:
                    self.last_update_id = updates[-1]['update_id']

                return updates
        except Exception as e:
            print(f"[ERROR] Error obteniendo updates: {e}")
            return []

    async def process_command(self, message):
        """Procesa comandos del mensaje"""
        text = message.get('text', '').strip()

        if text == '/limpiar':
            await self.handle_clean_command(message)
        elif text == '/ayuda':
            await self.handle_help_command(message)

    async def handle_clean_command(self, message):
        """Maneja el comando /limpiar"""
        message_id = message.get('message_id')

        print(f"\n[LIMPIAR] Comando recibido para limpiar el canal")
        print(f"[INFO] Buscando y eliminando mensajes del bot...")

        async with httpx.AsyncClient() as client:
            # Obtener información del canal
            r = await client.post(
                f"{self.api_url}/getChat",
                json={"chat_id": self.chat_id},
                timeout=15
            )

            if r.status_code == 200:
                chat_info = r.json().get('result', {})
                print(f"[INFO] Canal: {chat_info.get('title', 'Desconocido')}")

            # Intentar eliminar los últimos 50 mensajes del bot (backwards)
            deleted_count = 0
            error_count = 0

            for msg_id in range(message_id - 1, max(message_id - 51, 0), -1):
                r = await client.post(
                    f"{self.api_url}/deleteMessage",
                    json={
                        "chat_id": self.chat_id,
                        "message_id": msg_id
                    },
                    timeout=5
                )

                if r.status_code == 200 and r.json().get('ok'):
                    deleted_count += 1
                    print(f"[OK] Mensaje {msg_id} eliminado")
                else:
                    error_count += 1
                    error_desc = r.json().get('description', 'Unknown error')
                    if 'CHAT_NOT_MODIFIED' not in error_desc and 'not found' not in error_desc:
                        print(f"[ERROR] No se pudo eliminar {msg_id}: {error_desc}")

            # Enviar confirmación
            if deleted_count > 0:
                confirmation = f"✅ Se eliminaron {deleted_count} mensajes"
            else:
                confirmation = f"⚠️ No se eliminaron mensajes. Verifica que el bot sea ADMINISTRADOR del canal"

            print(f"\n{confirmation}\n")

            await client.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": confirmation,
                    "parse_mode": "HTML"
                },
                timeout=15
            )

    async def handle_help_command(self, message):
        """Maneja el comando /ayuda"""
        help_text = """
🤖 COMANDOS DISPONIBLES

/limpiar — Elimina los últimos 50 mensajes del canal
/ayuda — Muestra este mensaje

Nota: Solo puedes usar estos comandos si eres admin del canal
        """.strip()

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": help_text,
                    "parse_mode": "HTML"
                },
                timeout=15
            )

    async def run(self):
        """Ejecuta el handler continuamente"""
        print("=" * 60)
        print("BOT DE COMANDOS — Telegram Commands Handler")
        print("=" * 60)
        print(f"\n[INFO] Escuchando comandos en canal {self.chat_id}")
        print("[INFO] Comandos: /limpiar, /ayuda")
        print("[INFO] Presiona Ctrl+C para detener\n")

        try:
            while True:
                updates = await self.get_updates()

                for update in updates:
                    if 'message' not in update:
                        continue

                    message = update['message']
                    text = message.get('text', '')

                    # Solo procesar mensajes que sean comandos
                    if text.startswith('/'):
                        user = message.get('from', {})
                        username = user.get('username', 'Desconocido')
                        print(f"\n[COMANDO] /{text[1:]} por @{username}")

                        await self.process_command(message)

                # Pequeña pausa para no saturar
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            print("\n\n[DETENIDO] Bot de comandos detenido")
        except Exception as e:
            print(f"\n[ERROR] Error en el handler: {e}")

async def main():
    handler = TelegramCommandHandler()
    await handler.run()

if __name__ == "__main__":
    asyncio.run(main())
