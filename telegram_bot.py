"""
Panel de Control en Telegram - Versión httpx (compatible con Python 3.14)
Controla el bot de noticias directamente desde tu móvil
"""

import os
import re
import asyncio
import logging
import json
import threading
import httpx
import yaml
import feedparser
from http.server import HTTPServer, BaseHTTPRequestHandler
from db_manager import DatabaseManager
from config import AI_MODELS, CATEGORIES, DEFAULT_SYSTEM_PROMPT


# ─── Health check HTTP (mantiene vivo el servicio en Render) ─────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

    def log_message(self, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

SOURCES_FILE = "sources.yaml"


def sync_yaml_to_db():
    """Sincroniza las fuentes de sources.yaml a la BD para que aparezcan en el panel."""
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            sources = yaml.safe_load(f)

        db = DatabaseManager()

        # RSS feeds
        for feed in sources.get("rss_feeds", []):
            category = feed.get("tags", ["default"])[0]
            db.add_source(feed["name"], "RSS Feed", feed["url"], category)

        # YouTube channels
        for ch in sources.get("youtube_channels", []):
            url = ch.get("channel_id", ch.get("handle", ""))
            db.add_source(ch["name"], "YouTube", url, "youtube")

        # Hacker News
        if sources.get("hackernews", {}).get("enabled", True):
            db.add_source("Hacker News", "Hacker News",
                         "https://hacker-news.firebaseio.com", "dev")

        # Reddit
        for sub in sources.get("reddit_subreddits", []):
            db.add_source(f"r/{sub['name']}", "Reddit",
                         f"https://reddit.com/r/{sub['name']}", "dev")

    except Exception as e:
        log.warning(f"Error sincronizando fuentes: {e}")

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Constantes ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TIMEOUT = 30

db = DatabaseManager()

# Estado de conversaciones por usuario
user_states = {}


# ════════════════════════════════════════════════════════════════════════════
# HELPERS TELEGRAM API
# ════════════════════════════════════════════════════════════════════════════

async def send_message(client: httpx.AsyncClient, chat_id: int, text: str, keyboard=None):
    """Envía un mensaje con teclado opcional."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})

    try:
        r = await client.post(f"{BASE_URL}/sendMessage", json=payload, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        log.error(f"Error enviando mensaje: {e}")
        return None


async def edit_message(client: httpx.AsyncClient, chat_id: int, message_id: int, text: str, keyboard=None):
    """Edita un mensaje existente."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})

    try:
        r = await client.post(f"{BASE_URL}/editMessageText", json=payload, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        log.error(f"Error editando mensaje: {e}")
        return None


async def answer_callback(client: httpx.AsyncClient, callback_id: str, text: str = ""):
    """Responde al callback query."""
    try:
        await client.post(
            f"{BASE_URL}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text},
            timeout=TIMEOUT,
        )
    except Exception as e:
        log.error(f"Error respondiendo callback: {e}")


async def get_updates(client: httpx.AsyncClient, offset: int = 0):
    """Obtiene actualizaciones del bot."""
    try:
        r = await client.get(
            f"{BASE_URL}/getUpdates",
            params={"offset": offset, "timeout": 20, "allowed_updates": ["message", "callback_query"]},
            timeout=25,
        )
        return r.json().get("result", [])
    except Exception as e:
        log.error(f"Error obteniendo updates: {e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
# MENÚ PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════

def main_menu_keyboard():
    return [
        [{"text": "📋 Gestión de Fuentes",      "callback_data": "menu_sources"}],
        [{"text": "📰 Curación de Noticias",     "callback_data": "menu_curation"}],
        [{"text": "🎥 Videos de YouTubers",      "callback_data": "menu_youtube"}],
        [{"text": "⚙️ Configuración",             "callback_data": "menu_config"}],
        [{"text": "📚 Historial",                 "callback_data": "menu_history"}],
        [{"text": "📊 Estadísticas",              "callback_data": "menu_stats"}],
        [{"text": "📋 Logs",                      "callback_data": "menu_logs"}],
    ]


async def show_main_menu(client, chat_id, message_id=None):
    text = (
        "🎛️ *Panel de Control - Tech Digest Bot*\n\n"
        "Controla tu bot de noticias desde el móvil.\n"
        "Elige una opción:"
    )
    keyboard = main_menu_keyboard()
    if message_id:
        await edit_message(client, chat_id, message_id, text, keyboard)
    else:
        await send_message(client, chat_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# 1. GESTIÓN DE FUENTES
# ════════════════════════════════════════════════════════════════════════════

async def show_sources_menu(client, chat_id, message_id):
    text = "📋 *Gestión de Fuentes*\n\nElige una opción:"
    keyboard = [
        [{"text": "➕ Agregar Fuente", "callback_data": "add_source"}],
        [{"text": "📊 Ver Todas", "callback_data": "list_sources"}],
        [{"text": "❌ Eliminar Fuente", "callback_data": "delete_source_menu"}],
        [{"text": "🔄 Activar / Desactivar", "callback_data": "toggle_source_menu"}],
        [{"text": "🏠 Menú Principal", "callback_data": "main_menu"}],
    ]
    await edit_message(client, chat_id, message_id, text, keyboard)


async def show_list_sources(client, chat_id, message_id):
    sources = db.get_sources()
    if not sources:
        text = "📭 *No hay fuentes configuradas*\n\nAgrega una con ➕"
    else:
        text = f"📋 *Fuentes Configuradas ({len(sources)})*\n\n"
        for s in sources:
            status = "✅" if s["enabled"] else "❌"
            text += f"{status} *{s['name']}*\n"
            text += f"   🔗 {s['source_type']} | 🏷️ {s['category']}\n\n"

    keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
    await edit_message(client, chat_id, message_id, text, keyboard)


async def show_delete_source_menu(client, chat_id, message_id):
    sources = db.get_sources()
    if not sources:
        text = "📭 *No hay fuentes para eliminar*"
        keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
    else:
        text = "❌ *Selecciona la fuente a eliminar:*"
        keyboard = []
        for s in sources[:8]:
            keyboard.append([{"text": f"🗑️ {s['name']}", "callback_data": f"del_{s['id']}"}])
        keyboard.append([{"text": "🏠 Menú Principal", "callback_data": "main_menu"}])
    await edit_message(client, chat_id, message_id, text, keyboard)


async def show_toggle_source_menu(client, chat_id, message_id):
    sources = db.get_sources()
    if not sources:
        text = "📭 *No hay fuentes configuradas*"
        keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
    else:
        text = "🔄 *Activar / Desactivar Fuente:*"
        keyboard = []
        for s in sources[:8]:
            status = "✅" if s["enabled"] else "❌"
            keyboard.append([{"text": f"{status} {s['name']}", "callback_data": f"toggle_{s['id']}"}])
        keyboard.append([{"text": "🏠 Menú Principal", "callback_data": "main_menu"}])
    await edit_message(client, chat_id, message_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# FLUJO: AGREGAR FUENTE (conversación multi-paso)
# ════════════════════════════════════════════════════════════════════════════

async def start_add_source(client, chat_id, message_id):
    """Paso 1: pedir nombre"""
    user_states[chat_id] = {"step": "add_source_name"}
    text = "➕ *Agregar Fuente - Paso 1/4*\n\n✏️ Escribe el *nombre* de la fuente:\n\n_(Ej: TechCrunch, Karpathy YouTube)_"
    keyboard = [[{"text": "❌ Cancelar", "callback_data": "menu_sources"}]]
    await edit_message(client, chat_id, message_id, text, keyboard)


async def add_source_ask_type(client, chat_id):
    """Paso 2: pedir tipo"""
    user_states[chat_id]["step"] = "add_source_type"
    text = "➕ *Agregar Fuente - Paso 2/4*\n\n🔗 Elige el *tipo* de fuente:"
    keyboard = [
        [{"text": "📡 RSS Feed", "callback_data": "srctype_RSS Feed"}],
        [{"text": "🎥 YouTube", "callback_data": "srctype_YouTube"}],
        [{"text": "🐦 Twitter/X", "callback_data": "srctype_Twitter/X"}],
        [{"text": "🤖 Reddit", "callback_data": "srctype_Reddit"}],
        [{"text": "🔧 Otra", "callback_data": "srctype_Otra"}],
        [{"text": "❌ Cancelar", "callback_data": "menu_sources"}],
    ]
    await send_message(client, chat_id, text, keyboard)


async def add_source_ask_url(client, chat_id):
    """Paso 3: pedir URL"""
    user_states[chat_id]["step"] = "add_source_url"
    text = "➕ *Agregar Fuente - Paso 3/4*\n\n🌐 Pega la *URL o usuario*:\n\n_(Ej: https://techcrunch.com/feed)_"
    keyboard = [[{"text": "❌ Cancelar", "callback_data": "menu_sources"}]]
    await send_message(client, chat_id, text, keyboard)


async def add_source_ask_category(client, chat_id):
    """Paso 4: pedir categoría"""
    user_states[chat_id]["step"] = "add_source_category"
    text = "➕ *Agregar Fuente - Paso 4/4*\n\n🏷️ Elige la *categoría*:"
    keyboard = [
        [{"text": "🤖 Inteligencia Artificial", "callback_data": "srccate_ia"}],
        [{"text": "💻 Desarrollo & Open Source", "callback_data": "srccate_dev"}],
        [{"text": "🦾 Robótica & Hardware", "callback_data": "srccate_robotica"}],
        [{"text": "🌍 Tech & Industria", "callback_data": "srccate_industria"}],
        [{"text": "❌ Cancelar", "callback_data": "menu_sources"}],
    ]
    await send_message(client, chat_id, text, keyboard)


async def finish_add_source(client, chat_id, category):
    """Guarda la fuente en BD"""
    state = user_states.get(chat_id, {})
    name = state.get("name", "")
    source_type = state.get("source_type", "")
    url = state.get("url", "")

    success = db.add_source(name=name, source_type=source_type, url=url, category=category)

    if success:
        text = (
            f"✅ *¡Fuente Agregada!*\n\n"
            f"📝 Nombre: {name}\n"
            f"🔗 Tipo: {source_type}\n"
            f"🌐 URL: `{url}`\n"
            f"🏷️ Categoría: {CATEGORIES.get(category, {}).get('name', category)}\n\n"
            f"El bot la incluirá desde mañana."
        )
    else:
        text = "❌ *Error*\n\nLa fuente ya existe o URL inválida."

    keyboard = [
        [{"text": "➕ Agregar Otra", "callback_data": "add_source"}],
        [{"text": "🏠 Menú Principal", "callback_data": "main_menu"}],
    ]
    user_states.pop(chat_id, None)
    await send_message(client, chat_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# 2. CURACIÓN DE NOTICIAS
# ════════════════════════════════════════════════════════════════════════════

async def show_curation_menu(client, chat_id, message_id):
    pending = db.get_pending_news()
    count = len(pending)

    if count == 0:
        text = "✅ *Sin Noticias Pendientes*\n\nTodas las noticias han sido revisadas."
    else:
        text = f"📰 *Curación de Noticias*\n\n*{count} noticias pendientes* de revisión.\n\n"
        for i, n in enumerate(pending[:5], 1):
            text += f"{i}. *{n['title'][:55]}*\n"
            text += f"   📍 {n['source']} | 🏷️ {n['category']}\n\n"
        if count > 5:
            text += f"_... y {count - 5} más_"

    keyboard = [
        [{"text": f"✅ Ver & Aprobar Todas ({count})", "callback_data": "review_news"}],
        [{"text": "📤 Enviar Todas a Telegram", "callback_data": "send_all_news"}],
        [{"text": "🏠 Menú Principal", "callback_data": "main_menu"}],
    ]
    await edit_message(client, chat_id, message_id, text, keyboard)


async def show_review_news(client, chat_id, message_id):
    pending = db.get_pending_news()

    if not pending:
        text = "✅ *Sin noticias pendientes*"
        keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
        await edit_message(client, chat_id, message_id, text, keyboard)
        return

    text = f"📋 *{len(pending)} Noticias Pendientes*\n\n"
    for i, n in enumerate(pending[:10], 1):
        text += f"*{i}. {n['title'][:60]}*\n"
        text += f"📍 {n['source']}\n"
        if n.get("url"):
            text += f"🔗 {n['url']}\n"
        text += "\n"

    keyboard = [
        [{"text": "✅ Aprobar Todas", "callback_data": "approve_all_news"}],
        [{"text": "🗑️ Descartar Todas", "callback_data": "discard_all_news"}],
        [{"text": "🏠 Menú Principal", "callback_data": "main_menu"}],
    ]
    await edit_message(client, chat_id, message_id, text, keyboard)


async def approve_all_news(client, chat_id, message_id):
    pending = db.get_pending_news()
    ids = [n["id"] for n in pending]
    if ids:
        for nid in ids:
            db.approve_news(nid)
        db.mark_sent(ids)
        text = f"✅ *{len(ids)} Noticias Aprobadas*\n\nYa están marcadas como enviadas."
    else:
        text = "✅ *Sin noticias pendientes*"

    keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
    await edit_message(client, chat_id, message_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# 3. CONFIGURACIÓN
# ════════════════════════════════════════════════════════════════════════════

async def show_config_menu(client, chat_id, message_id):
    current_model = db.get_config("ai_model", "claude-sonnet-4-20250514")
    model_name = AI_MODELS.get(current_model, {}).get("name", current_model)

    text = (
        f"⚙️ *Configuración*\n\n"
        f"🤖 Modelo actual: *{model_name}*\n\n"
        f"Elige qué configurar:"
    )
    keyboard = [
        [{"text": "🤖 Cambiar Modelo IA", "callback_data": "change_model"}],
        [{"text": "📝 Ver Prompt Completo", "callback_data": "view_prompt"}],
        [{"text": "✏️ Editar Prompt", "callback_data": "edit_prompt"}],
        [{"text": "🔄 Restaurar Prompt Original", "callback_data": "reset_prompt"}],
        [{"text": "🏷️ Gestionar Categorías", "callback_data": "manage_categories"}],
        [{"text": "🏠 Menú Principal", "callback_data": "main_menu"}],
    ]
    await edit_message(client, chat_id, message_id, text, keyboard)


async def show_full_prompt(client, chat_id, message_id):
    """Muestra el prompt completo dividido en partes si es necesario."""
    prompt = db.get_config("system_prompt", DEFAULT_SYSTEM_PROMPT)

    # Telegram limita mensajes a 4096 chars — dividimos si hace falta
    parts = [prompt[i:i+3800] for i in range(0, len(prompt), 3800)]

    keyboard = [
        [{"text": "✏️ Editar Prompt", "callback_data": "edit_prompt"}],
        [{"text": "🔄 Restaurar Original", "callback_data": "reset_prompt"}],
        [{"text": "🏠 Menú Principal", "callback_data": "main_menu"}],
    ]

    # Primero editar el mensaje actual con la parte 1
    header = f"📝 *Prompt del Sistema* ({len(prompt)} chars)\n\n"
    await edit_message(client, chat_id, message_id, header + f"```\n{parts[0]}\n```", keyboard if len(parts) == 1 else None)

    # Si hay más partes, enviarlas como mensajes adicionales
    for i, part in enumerate(parts[1:], 2):
        is_last = i == len(parts)
        await send_message(
            client, chat_id,
            f"_...parte {i}/{len(parts)}..._\n\n```\n{part}\n```",
            keyboard if is_last else None
        )


async def show_change_model(client, chat_id, message_id):
    text = "🤖 *Elige el Modelo de IA*\n\n"
    for model_id, info in AI_MODELS.items():
        text += f"*{info['name']}*\n"
        text += f"  ⚡ {info['speed']} | 💎 {info['quality']}\n"
        cost = info['cost_per_1m_tokens']['input']
        text += f"  💰 ${cost:.3f}/1M tokens entrada\n\n"

    keyboard = []
    for model_id, info in AI_MODELS.items():
        keyboard.append([{"text": info["name"], "callback_data": f"setmodel_{model_id}"}])
    keyboard.append([{"text": "🏠 Menú Principal", "callback_data": "main_menu"}])
    await edit_message(client, chat_id, message_id, text, keyboard)


async def show_manage_categories(client, chat_id, message_id):
    text = "🏷️ *Gestionar Categorías*\n\nToca para activar / desactivar:\n\n"
    keyboard = []
    for cat_key, cat_info in CATEGORIES.items():
        saved = db.get_config(f"category_{cat_key}_enabled", "True")
        active = saved.lower() == "true"
        status = "✅" if active else "❌"
        text += f"{status} {cat_info['name']}\n"
        label = f"{status} {cat_info['name']}"
        keyboard.append([{"text": label, "callback_data": f"togglecat_{cat_key}"}])

    keyboard.append([{"text": "🏠 Menú Principal", "callback_data": "main_menu"}])
    await edit_message(client, chat_id, message_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# 🎥 VIDEOS DE YOUTUBERS
# ════════════════════════════════════════════════════════════════════════════

def get_youtube_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/)([^&\s?]+)", url)
    return m.group(1) if m else None


async def fetch_youtube_videos(client: httpx.AsyncClient, max_per_channel: int = 3) -> list[dict]:
    """Obtiene los últimos videos de todos los canales YouTube configurados."""
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources = yaml.safe_load(f)

    channels = sources.get("youtube_channels", [])
    videos = []
    headers = {"User-Agent": "TechDigestBot/2.0"}

    for ch in channels:
        channel_id = ch.get("channel_id", "")
        handle     = ch.get("handle", "")
        name       = ch.get("name", "")

        # Resolver handle si no hay channel_id
        if not channel_id and handle:
            h = handle.lstrip("@")
            try:
                res = db.client.table("youtube_handles").select("channel_id").eq("handle", f"@{h}").execute()
                if res.data:
                    channel_id = res.data[0]["channel_id"]
            except Exception:
                pass

        if not channel_id:
            continue

        try:
            url  = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            r    = await client.get(url, headers=headers, timeout=10)
            feed = feedparser.parse(r.text)

            for entry in feed.entries[:max_per_channel]:
                video_url = entry.get("link", "")
                vid_id    = get_youtube_video_id(video_url)
                videos.append({
                    "channel": name,
                    "title":   entry.get("title", "Sin título"),
                    "url":     video_url,
                    "thumb":   f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg" if vid_id else "",
                    "date":    entry.get("published", "")[:10],
                })
        except Exception:
            continue

    return videos


async def show_youtube_menu(client, chat_id, message_id):
    """Menú de opciones para videos YouTube."""
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources = yaml.safe_load(f)
    n_channels = len(sources.get("youtube_channels", []))

    text = (
        f"🎥 *Videos de YouTubers*\n\n"
        f"Tienes *{n_channels} canales* configurados.\n\n"
        f"Elige cuántos videos por canal quieres ver:"
    )
    keyboard = [
        [{"text": "▶️ Último video de cada canal",     "callback_data": "yt_send_1"}],
        [{"text": "▶️▶️ Últimos 3 videos por canal",   "callback_data": "yt_send_3"}],
        [{"text": "📋 Solo listar (sin enviar al canal)", "callback_data": "yt_list"}],
        [{"text": "🏠 Menú Principal",                 "callback_data": "main_menu"}],
    ]
    await edit_message(client, chat_id, message_id, text, keyboard)


async def send_youtube_videos_to_channel(client, chat_id, message_id, max_per_channel: int):
    """Envía los videos al canal de Telegram visualmente."""
    await edit_message(client, chat_id, message_id,
        "⏳ *Obteniendo videos...*\nEsto puede tardar unos segundos.",
        [[{"text": "⏳ Cargando...", "callback_data": "main_menu"}]]
    )

    async with httpx.AsyncClient(follow_redirects=True) as fetch_client:
        videos = await fetch_youtube_videos(fetch_client, max_per_channel)

    if not videos:
        await edit_message(client, chat_id, message_id,
            "❌ No se pudieron obtener videos.",
            [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
        )
        return

    # Enviar separador al canal
    await client.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🎥 <b>Videos de tus YouTubers — {len(videos)} videos</b>",
        "parse_mode": "HTML",
    }, timeout=15)

    sent = 0
    for v in videos:
        vid_id = get_youtube_video_id(v["url"])
        caption = (
            f"🎥 <b>{v['title'][:100]}</b>\n\n"
            f"📍 <i>{v['channel']}</i>\n"
            f"📅 {v['date']}\n"
            f"🔗 {v['url']}"
        )
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": [[{"text": "▶️ Ver Video", "url": v["url"]}]]},
        }
        if v["thumb"]:
            payload["photo"] = v["thumb"]
            r = await client.post(f"{BASE_URL}/sendPhoto", json=payload, timeout=15)
        else:
            payload["text"] = caption
            r = await client.post(f"{BASE_URL}/sendMessage", json=payload, timeout=15)

        if r.json().get("ok"):
            sent += 1
        await asyncio.sleep(1)

    # Confirmar en el chat privado
    await edit_message(client, chat_id, message_id,
        f"✅ *{sent} videos enviados al canal*",
        [[{"text": "🎥 Ver más videos", "callback_data": "menu_youtube"},
          {"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
    )


async def list_youtube_videos(client, chat_id, message_id):
    """Lista los videos en el chat privado (sin enviar al canal)."""
    await edit_message(client, chat_id, message_id,
        "⏳ *Obteniendo videos...*", None)

    async with httpx.AsyncClient(follow_redirects=True) as fetch_client:
        videos = await fetch_youtube_videos(fetch_client, max_per_channel=2)

    if not videos:
        text = "❌ No se encontraron videos."
    else:
        text = f"🎥 *Últimos videos ({len(videos)})*\n\n"
        for v in videos:
            text += f"*{v['channel']}*\n"
            text += f"📹 [{v['title'][:60]}]({v['url']})\n"
            text += f"📅 {v['date']}\n\n"

    keyboard = [
        [{"text": "📤 Enviar al Canal", "callback_data": "yt_send_1"}],
        [{"text": "🏠 Menú Principal",  "callback_data": "main_menu"}],
    ]
    await edit_message(client, chat_id, message_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# 4. HISTORIAL
# ════════════════════════════════════════════════════════════════════════════

async def show_history(client, chat_id, message_id):
    history = db.get_news_history(limit=10)

    if not history:
        text = "📭 *No hay historial todavía*\n\nLas noticias enviadas aparecerán aquí."
    else:
        text = f"📚 *Últimas {len(history)} Noticias Enviadas*\n\n"
        for i, n in enumerate(history, 1):
            date = n.get("sent_at", "")[:10] if n.get("sent_at") else ""
            text += f"{i}. *{n['title'][:55]}*\n"
            text += f"   📍 {n['source']} | 📅 {date}\n\n"

    keyboard = [
        [{"text": "🔍 Buscar Noticia", "callback_data": "search_news"}],
        [{"text": "🏠 Menú Principal", "callback_data": "main_menu"}],
    ]
    await edit_message(client, chat_id, message_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# 5. ESTADÍSTICAS
# ════════════════════════════════════════════════════════════════════════════

async def show_stats(client, chat_id, message_id):
    stats = db.get_statistics()

    text = "📊 *Estadísticas del Bot*\n\n"
    text += f"📨 Total enviadas: *{stats['total_sent']}*\n"
    text += f"✅ Tasa de aprobación: *{stats['approval_rate']:.1f}%*\n"
    text += f"📚 Fuentes activas: *{len(db.get_sources(enabled_only=True))}*\n\n"

    if stats["by_category"]:
        text += "*Por Categoría:*\n"
        for cat, count in stats["by_category"].items():
            cat_name = CATEGORIES.get(cat, {}).get("name", cat)
            text += f"  {cat_name}: {count}\n"
        text += "\n"

    if stats["by_source"]:
        text += "*Top 5 Fuentes:*\n"
        for i, (source, count) in enumerate(list(stats["by_source"].items())[:5], 1):
            text += f"  {i}. {source}: {count}\n"

    keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
    await edit_message(client, chat_id, message_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# 6. LOGS
# ════════════════════════════════════════════════════════════════════════════

async def show_logs(client, chat_id, message_id):
    logs = db.get_logs(limit=15)

    if not logs:
        text = "📭 *No hay logs disponibles*"
    else:
        text = "📋 *Últimos Eventos del Sistema*\n\n"
        icons = {"SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "INFO": "ℹ️"}
        for log_entry in logs:
            icon = icons.get(log_entry["level"], "📌")
            ts = log_entry["timestamp"][:16] if log_entry.get("timestamp") else ""
            text += f"{icon} `{ts}`\n"
            text += f"   {log_entry['message']}\n\n"

    keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
    await edit_message(client, chat_id, message_id, text, keyboard)


# ════════════════════════════════════════════════════════════════════════════
# COMANDO /clear
# ════════════════════════════════════════════════════════════════════════════

async def handle_clear_command(client, chat_id):
    if not TELEGRAM_CHAT_ID:
        await send_message(client, chat_id, "❌ TELEGRAM_CHAT_ID no configurado")
        return
    try:
        r = await client.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✨ <b>CANAL LIMPIADO</b> ✨\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📢 Nuevas noticias comenzarán desde aquí.",
                "parse_mode": "HTML",
            },
            timeout=15,
        )
        if r.json().get("ok"):
            keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
            await send_message(client, chat_id,
                "✅ *Canal limpiado*\n\nSe envió un separador visual a tu canal.\n\n"
                "⚠️ Los mensajes anteriores permanecen, puedes borrarlos manualmente.", keyboard)
        else:
            desc = r.json().get("description", "Error desconocido")
            await send_message(client, chat_id, f"❌ Error: {desc}")
    except Exception as e:
        await send_message(client, chat_id, f"❌ Error: {str(e)[:100]}")


# ════════════════════════════════════════════════════════════════════════════
# PROCESADOR DE MENSAJES (texto libre)
# ════════════════════════════════════════════════════════════════════════════

async def handle_text_message(client, chat_id, text):
    """Maneja mensajes de texto según el estado del usuario."""
    state = user_states.get(chat_id, {})
    step = state.get("step", "")

    if step == "add_source_name":
        user_states[chat_id]["name"] = text
        await add_source_ask_type(client, chat_id)

    elif step == "add_source_url":
        user_states[chat_id]["url"] = text
        await add_source_ask_category(client, chat_id)

    elif step == "edit_prompt":
        db.set_config("system_prompt", text)
        user_states.pop(chat_id, None)
        keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
        await send_message(client, chat_id, "✅ *Prompt guardado correctamente*", keyboard)

    elif step == "search_news":
        results = db.search_news(text)
        user_states.pop(chat_id, None)
        if results:
            reply = f"🔍 *{len(results)} Resultados para '{text}'*\n\n"
            for i, n in enumerate(results[:8], 1):
                reply += f"{i}. *{n['title'][:55]}*\n"
                reply += f"   📍 {n['source']}\n"
                if n.get("url"):
                    reply += f"   🔗 {n['url']}\n"
                reply += "\n"
        else:
            reply = f"🔍 *Sin resultados para '{text}'*"

        keyboard = [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]]
        await send_message(client, chat_id, reply, keyboard)

    else:
        # Sin estado activo → mostrar menú
        keyboard = [[{"text": "🎛️ Abrir Panel", "callback_data": "main_menu"}]]
        await send_message(
            client, chat_id,
            "👋 Usa el panel de control para gestionar tu bot:",
            keyboard,
        )


# ════════════════════════════════════════════════════════════════════════════
# PROCESADOR DE CALLBACKS (botones)
# ════════════════════════════════════════════════════════════════════════════

async def handle_callback(client, callback):
    """Procesa todos los botones pulsados."""
    cb_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    data = callback.get("data", "")

    await answer_callback(client, cb_id)

    # ─── Menú principal ───────────────────────────────────────────────────
    if data == "main_menu":
        user_states.pop(chat_id, None)
        await show_main_menu(client, chat_id, message_id)

    # ─── Fuentes ──────────────────────────────────────────────────────────
    elif data == "menu_sources":
        await show_sources_menu(client, chat_id, message_id)
    elif data == "add_source":
        await start_add_source(client, chat_id, message_id)
    elif data == "list_sources":
        await show_list_sources(client, chat_id, message_id)
    elif data == "delete_source_menu":
        await show_delete_source_menu(client, chat_id, message_id)
    elif data == "toggle_source_menu":
        await show_toggle_source_menu(client, chat_id, message_id)
    elif data.startswith("del_"):
        source_id = int(data.split("_")[1])
        db.delete_source(source_id)
        await answer_callback(client, cb_id, "✅ Fuente eliminada")
        await show_sources_menu(client, chat_id, message_id)
    elif data.startswith("toggle_"):
        source_id = int(data.split("_")[1])
        db.toggle_source(source_id)
        await show_toggle_source_menu(client, chat_id, message_id)
    elif data.startswith("srctype_"):
        source_type = data[len("srctype_"):]
        user_states[chat_id]["source_type"] = source_type
        await add_source_ask_url(client, chat_id)
    elif data.startswith("srccate_"):
        category = data[len("srccate_"):]
        await finish_add_source(client, chat_id, category)

    # ─── Curación ─────────────────────────────────────────────────────────
    elif data == "menu_curation":
        await show_curation_menu(client, chat_id, message_id)
    elif data == "review_news":
        await show_review_news(client, chat_id, message_id)
    elif data in ("approve_all_news", "send_all_news"):
        await approve_all_news(client, chat_id, message_id)
    elif data == "discard_all_news":
        pending = db.get_pending_news()
        db.mark_sent([n["id"] for n in pending])
        await edit_message(client, chat_id, message_id, "🗑️ *Noticias descartadas*", [[{"text": "🏠 Menú Principal", "callback_data": "main_menu"}]])

    # ─── Configuración ────────────────────────────────────────────────────
    elif data == "menu_config":
        await show_config_menu(client, chat_id, message_id)
    elif data == "change_model":
        await show_change_model(client, chat_id, message_id)
    elif data.startswith("setmodel_"):
        model_id = data[len("setmodel_"):]
        db.set_config("ai_model", model_id)
        model_name = AI_MODELS.get(model_id, {}).get("name", model_id)
        await answer_callback(client, cb_id, f"✅ Modelo: {model_name}")
        await show_config_menu(client, chat_id, message_id)
    elif data == "view_prompt":
        await show_full_prompt(client, chat_id, message_id)
    elif data == "edit_prompt":
        user_states[chat_id] = {"step": "edit_prompt"}
        text = (
            "✏️ *Editar Prompt del Sistema*\n\n"
            "Escribe el nuevo prompt completo y envíalo.\n\n"
            "_Tip: Puedes copiar el prompt actual con_ *Ver Prompt Completo* _y modificarlo._"
        )
        keyboard = [[{"text": "❌ Cancelar", "callback_data": "menu_config"}]]
        await edit_message(client, chat_id, message_id, text, keyboard)
    elif data == "reset_prompt":
        db.set_config("system_prompt", DEFAULT_SYSTEM_PROMPT)
        await answer_callback(client, cb_id, "✅ Prompt restaurado al original")
        await show_config_menu(client, chat_id, message_id)
    elif data == "manage_categories":
        await show_manage_categories(client, chat_id, message_id)
    elif data.startswith("togglecat_"):
        cat_key = data[len("togglecat_"):]
        current = db.get_config(f"category_{cat_key}_enabled", "True")
        new_val = "False" if current.lower() == "true" else "True"
        db.set_config(f"category_{cat_key}_enabled", new_val)
        status = "✅ Activada" if new_val == "True" else "❌ Desactivada"
        cat_name = CATEGORIES.get(cat_key, {}).get("name", cat_key)
        await answer_callback(client, cb_id, f"{status}: {cat_name}")
        await show_manage_categories(client, chat_id, message_id)

    # ─── Historial ────────────────────────────────────────────────────────
    elif data == "menu_history":
        await show_history(client, chat_id, message_id)
    elif data == "search_news":
        user_states[chat_id] = {"step": "search_news"}
        keyboard = [[{"text": "❌ Cancelar", "callback_data": "menu_history"}]]
        await edit_message(client, chat_id, message_id, "🔍 *Escribe la palabra a buscar:*", keyboard)

    # ─── Videos YouTube ───────────────────────────────────────────────────
    elif data == "menu_youtube":
        await show_youtube_menu(client, chat_id, message_id)
    elif data == "yt_send_1":
        await send_youtube_videos_to_channel(client, chat_id, message_id, max_per_channel=1)
    elif data == "yt_send_3":
        await send_youtube_videos_to_channel(client, chat_id, message_id, max_per_channel=3)
    elif data == "yt_list":
        await list_youtube_videos(client, chat_id, message_id)

    # ─── Estadísticas ─────────────────────────────────────────────────────
    elif data == "menu_stats":
        await show_stats(client, chat_id, message_id)

    # ─── Logs ─────────────────────────────────────────────────────────────
    elif data == "menu_logs":
        await show_logs(client, chat_id, message_id)


# ════════════════════════════════════════════════════════════════════════════
# BUCLE PRINCIPAL (Long Polling)
# ════════════════════════════════════════════════════════════════════════════

async def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN no configurado")
        return

    print("=" * 40)
    print("Tech Digest Bot - Panel de Control")
    print(f"Token: {TELEGRAM_BOT_TOKEN[:20]}...")
    print("=" * 40)
    print("Bot activo. Escribe /start en Telegram")
    print("(chat PRIVADO con tu bot, no en el canal)")
    print("=" * 40)

    # Arrancar health server en segundo plano (para Koyeb)
    threading.Thread(target=start_health_server, daemon=True).start()
    print(f"Health server activo en puerto {os.environ.get('PORT', 8080)}")

    # Sincronizar fuentes de sources.yaml a la BD
    sync_yaml_to_db()
    print("Fuentes sincronizadas desde sources.yaml")

    offset = 0

    async with httpx.AsyncClient() as client:
        while True:
            try:
                updates = await get_updates(client, offset)

                for update in updates:
                    offset = update["update_id"] + 1

                    # Mensaje de texto
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")

                        if text == "/start":
                            await show_main_menu(client, chat_id)
                        elif text == "/clear":
                            await handle_clear_command(client, chat_id)
                        elif text.startswith("/"):
                            pass  # Ignorar otros comandos
                        else:
                            await handle_text_message(client, chat_id, text)

                    # Botón pulsado
                    elif "callback_query" in update:
                        await handle_callback(client, update["callback_query"])

            except Exception as e:
                log.error(f"Error en bucle principal: {e}")
                await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
