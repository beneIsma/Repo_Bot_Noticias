"""
Gestor de Base de Datos — Supabase (PostgreSQL online)
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Any

from supabase import create_client, Client

log = logging.getLogger(__name__)

# ─── Credenciales ────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    "https://clbndfpymrzzmascetlr.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNsYm5kZnB5bXJ6em1hc2NldGxyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA0MTcyMDEsImV4cCI6MjA5NTk5MzIwMX0.Z35AP0GyKKrTIee2QoZCdt1T3ELVJNdfQ92caG5H_Bg"
)


def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


class DatabaseManager:
    """Gestor de base de datos Supabase para el bot de noticias."""

    def __init__(self):
        self.client = get_client()

    # ─── GESTIÓN DE FUENTES ─────────────────────────────────────────────────

    def add_source(
        self, name: str, source_type: str, url: str, category: str
    ) -> bool:
        try:
            self.client.table("sources").insert({
                "name": name,
                "source_type": source_type,
                "url": url,
                "category": category,
                "enabled": True,
            }).execute()
            self.add_log("SUCCESS", f"Fuente añadida: {name}")
            return True
        except Exception as e:
            # Ignorar error de duplicado (unique constraint)
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                return False
            self.add_log("ERROR", f"Error al añadir fuente: {str(e)[:100]}")
            return False

    def get_sources(self, enabled_only: bool = False) -> List[Dict]:
        try:
            query = self.client.table("sources").select("*").order("id")
            if enabled_only:
                query = query.eq("enabled", True)
            res = query.execute()
            return res.data or []
        except Exception as e:
            log.error(f"Error obteniendo fuentes: {e}")
            return []

    def delete_source(self, source_id: int) -> bool:
        try:
            row = self.client.table("sources").select("name").eq("id", source_id).execute()
            name = row.data[0]["name"] if row.data else "Desconocida"
            self.client.table("sources").delete().eq("id", source_id).execute()
            self.add_log("SUCCESS", f"Fuente eliminada: {name}")
            return True
        except Exception as e:
            self.add_log("ERROR", f"Error al eliminar fuente: {str(e)[:100]}")
            return False

    def toggle_source(self, source_id: int) -> bool:
        try:
            row = self.client.table("sources").select("enabled").eq("id", source_id).execute()
            if not row.data:
                return False
            current = row.data[0]["enabled"]
            self.client.table("sources").update({"enabled": not current}).eq("id", source_id).execute()
            return True
        except Exception as e:
            self.add_log("ERROR", f"Error al cambiar estado: {str(e)[:100]}")
            return False

    # ─── GESTIÓN DE NOTICIAS ───────────────────────────────────────────────

    def add_news(
        self, title: str, url: str, source: str,
        category: str, summary: str = ""
    ) -> bool:
        try:
            self.client.table("news").insert({
                "title": title,
                "url": url,
                "source": source,
                "category": category,
                "summary": summary,
                "status": "pending",
                "approved": False,
            }).execute()
            return True
        except Exception as e:
            log.error(f"Error al añadir noticia: {e}")
            return False

    def get_pending_news(self) -> List[Dict]:
        try:
            res = self.client.table("news")\
                .select("*")\
                .eq("status", "pending")\
                .eq("approved", False)\
                .order("id", desc=True)\
                .execute()
            return res.data or []
        except Exception as e:
            log.error(f"Error obteniendo noticias: {e}")
            return []

    def approve_news(self, news_id: int) -> bool:
        try:
            self.client.table("news").update({
                "approved": True,
                "approved_at": datetime.utcnow().isoformat(),
            }).eq("id", news_id).execute()
            return True
        except Exception as e:
            log.error(f"Error al aprobar noticia: {e}")
            return False

    def mark_sent(self, news_ids: List[int]) -> bool:
        try:
            for news_id in news_ids:
                self.client.table("news").update({
                    "status": "sent",
                    "sent_at": datetime.utcnow().isoformat(),
                }).eq("id", news_id).execute()
            self.add_log("SUCCESS", f"{len(news_ids)} noticias marcadas como enviadas")
            return True
        except Exception as e:
            log.error(f"Error al marcar como enviadas: {e}")
            return False

    def search_news(self, query: str) -> List[Dict]:
        try:
            res = self.client.table("news")\
                .select("*")\
                .ilike("title", f"%{query}%")\
                .order("id", desc=True)\
                .limit(50)\
                .execute()
            return res.data or []
        except Exception as e:
            log.error(f"Error buscando noticias: {e}")
            return []

    def get_news_history(self, limit: int = 100) -> List[Dict]:
        try:
            res = self.client.table("news")\
                .select("*")\
                .eq("status", "sent")\
                .order("id", desc=True)\
                .limit(limit)\
                .execute()
            return res.data or []
        except Exception as e:
            log.error(f"Error obteniendo historial: {e}")
            return []

    # ─── GESTIÓN DE CONFIGURACIÓN ──────────────────────────────────────────

    def set_config(self, key: str, value: str) -> bool:
        try:
            self.client.table("config").upsert({
                "key": key,
                "value": value,
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()
            return True
        except Exception as e:
            log.error(f"Error al guardar config: {e}")
            return False

    def get_config(self, key: str, default: str = "") -> str:
        try:
            res = self.client.table("config").select("value").eq("key", key).execute()
            return res.data[0]["value"] if res.data else default
        except Exception:
            return default

    # ─── GESTIÓN DE LOGS ───────────────────────────────────────────────────

    def add_log(self, level: str, message: str) -> None:
        try:
            self.client.table("logs").insert({
                "level": level,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
            }).execute()
        except Exception:
            pass

    def get_logs(self, limit: int = 50) -> List[Dict]:
        try:
            res = self.client.table("logs")\
                .select("level, message, timestamp")\
                .order("id", desc=True)\
                .limit(limit)\
                .execute()
            return res.data or []
        except Exception as e:
            log.error(f"Error obteniendo logs: {e}")
            return []

    # ─── ESTADÍSTICAS ──────────────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, Any]:
        try:
            total_res = self.client.table("news").select("id", count="exact").eq("status", "sent").execute()
            total_sent = total_res.count or 0

            cat_res = self.client.table("news").select("category").eq("status", "sent").execute()
            by_category: Dict[str, int] = {}
            for row in (cat_res.data or []):
                cat = row.get("category", "unknown")
                by_category[cat] = by_category.get(cat, 0) + 1

            src_res = self.client.table("news").select("source").eq("status", "sent").execute()
            by_source: Dict[str, int] = {}
            for row in (src_res.data or []):
                src = row.get("source", "unknown")
                by_source[src] = by_source.get(src, 0) + 1
            by_source = dict(sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:10])

            approved_res = self.client.table("news").select("id", count="exact")\
                .eq("approved", True).eq("status", "sent").execute()
            approved = approved_res.count or 0
            approval_rate = (approved / total_sent * 100) if total_sent > 0 else 0

            return {
                "total_sent": total_sent,
                "by_category": by_category,
                "by_source": by_source,
                "approval_rate": approval_rate,
            }
        except Exception as e:
            log.error(f"Error obteniendo estadísticas: {e}")
            return {"total_sent": 0, "by_category": {}, "by_source": {}, "approval_rate": 0}

    def clear_old_news(self, days: int = 30) -> int:
        try:
            from datetime import timedelta
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            res = self.client.table("news").delete().lt("sent_at", cutoff).execute()
            deleted = len(res.data or [])
            self.add_log("SUCCESS", f"Limpiadas {deleted} noticias antiguas")
            return deleted
        except Exception as e:
            log.error(f"Error al limpiar noticias: {e}")
            return 0

    def clear_all_news(self) -> int:
        """Elimina TODAS las noticias de la base de datos. ⚠️ DESTRUCTIVO."""
        try:
            res = self.client.table("news").select("id").execute()
            total = len(res.data or [])
            if total == 0:
                self.add_log("INFO", "No hay noticias para eliminar")
                return 0

            # Eliminar por lotes para evitar limites
            for chunk in [res.data[i:i+1000] for i in range(0, len(res.data), 1000)]:
                ids = [row["id"] for row in chunk]
                for news_id in ids:
                    self.client.table("news").delete().eq("id", news_id).execute()

            self.add_log("SUCCESS", f"Eliminadas {total} noticias (LIMPIEZA COMPLETA)")
            return total
        except Exception as e:
            self.add_log("ERROR", f"Error eliminando noticias: {str(e)[:100]}")
            return 0
