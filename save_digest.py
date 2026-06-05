#!/usr/bin/env python3
"""Ejecuta el bot y guarda el digest en un archivo"""

import os
import sys
import io
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# UTF-8 en Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

# Importar funciones del bot
from bot_v2 import (
    load_sources, collect_all_news, build_user_message, call_claude, SOURCES_FILE
)

async def main():
    print("=" * 60)
    print("GENERANDO DIGEST - GUARDANDO EN ARCHIVO")
    print("=" * 60)

    # Cargar y recopilar
    print("\n[1/3] Cargando fuentes...")
    sources = load_sources(SOURCES_FILE)

    print("[2/3] Recopilando articulos...")
    articles = await collect_all_news(sources)

    if not articles:
        print("ERROR: No se obtuvieron articulos")
        return

    print(f"[OK] {len(articles)} articulos recopilados")

    print("[3/3] Procesando con Claude...")
    user_message = build_user_message(articles)
    digest = await call_claude(user_message)

    # Guardar en archivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"digest_{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(digest)

    print(f"\n[OK] Digest guardado en: {filename}")
    print(f"[OK] Caracteres: {len(digest)}")
    print("\n" + "=" * 60)
    print("CONTENIDO DEL DIGEST:")
    print("=" * 60)
    print(digest)
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
