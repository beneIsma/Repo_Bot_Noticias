#!/usr/bin/env python3
"""
Script de limpieza de base de datos — Elimina todas las noticias
DESTRUCTIVO: No se puede deshacer
"""

import os
import sys
import io

# Configurar UTF-8 en Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from db_manager import DatabaseManager

def main():
    print("=" * 60)
    print("[LIMPIEZA] BASE DE DATOS")
    print("=" * 60)
    print("\nADVERTENCIA: Esta acción es IRREVERSIBLE")
    print("Se eliminarán TODAS las noticias de la base de datos.\n")

    # Si está en modo batch, aceptar --confirm
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        print("[AUTO] Confirmación automática activada")
    else:
        try:
            response = input("¿Estás seguro? Escribe 'SI' para confirmar: ").strip().upper()
            if response != "SI":
                print("\n[CANCELADO] Operación cancelada")
                sys.exit(0)
        except EOFError:
            # En modo no-interactivo (GitHub Actions), usar --confirm
            print("[ERROR] No se puede leer entrada. Usa: python cleanup_db.py --confirm")
            sys.exit(1)

    print("\n[CONEXION] Conectando a Supabase...")
    db = DatabaseManager()

    print("[ELIMINANDO] Todas las noticias...")
    deleted = db.clear_all_news()

    print(f"\n[OK] Limpieza completada:")
    print(f"   • Noticias eliminadas: {deleted}")
    print(f"   • Base de datos lista para empezar de cero")
    print(f"   • Logs registrados en Supabase")

    print("\n[LISTO] El bot está listo para recolectar noticias nuevas.")
    print("   Próxima ejecución: en 1 hora (GitHub Actions)")

if __name__ == "__main__":
    main()
