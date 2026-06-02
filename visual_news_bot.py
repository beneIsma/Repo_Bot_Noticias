"""
Visual News Bot — Envía noticias y videos al canal de Telegram con formato visual.
Cada artículo = imagen + descripción + botón URL.
Cada video = thumbnail + descripción + botón.
Ejecuta cada 2 horas y solo envía contenido nuevo.
"""

import os
import re
import json
import asyncio
import logging
from datetime import datetime

import httpx
import feedparser
import yaml
from supabase import create_client

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Constantes ─────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
GROQ_API_KEY        = os.environ.get("GROQ_API_KEY", "")
SUPABASE_URL        = os.environ.get("SUPABASE_URL", "https://clbndfpymrzzmascetlr.supabase.co")
SUPABASE_KEY        = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNsYm5kZnB5bXJ6em1hc2NldGxyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA0MTcyMDEsImV4cCI6MjA5NTk5MzIwMX0.Z35AP0GyKKrTIee2QoZCdt1T3ELVJNdfQ92caG5H_Bg")
GROQ_MODEL_FAST     = "llama-3.1-8b-instant"     # Para traducciones (rápido)
TRANSLATE_BATCH     = 10
BASE_URL            = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
SOURCES_FILE        = "sources.yaml"

# Cliente Supabase
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
REQUEST_TIMEOUT    = 15
MAX_ITEMS          = 3        # Máx artículos por fuente por ejecución
MAX_ITEMS_PER_RUN  = 10       # Máx noticias a enviar en total por ejecución
DELAY_BETWEEN_MSGS = 4        # Segundos entre mensajes (evitar flood Telegram)

# Emojis por categoría
CAT_EMOJI = {
    "ia":        "🤖",
    "dev":       "💻",
    "robotica":  "🦾",
    "industria": "🌍",
    "youtube":   "🎥",
    "default":   "📰",
}

# Imagen fallback por categoría (imágenes públicas de Unsplash)
FALLBACK_IMAGES = {
    "ia":        "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=800",
    "dev":       "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=800",
    "robotica":  "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=800",
    "industria": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800",
    "youtube":   "https://images.unsplash.com/photo-1611532736597-de2d4265fba3?w=800",
    "default":   "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800",
}


# ════════════════════════════════════════════════════════════════════════════
# BASE DE DATOS — rastreo de URLs enviadas
# ════════════════════════════════════════════════════════════════════════════

def init_sent_db():
    """Con Supabase las tablas ya existen — no hace falta inicializar."""
    pass


def get_cached_channel_id(handle: str) -> str | None:
    """Devuelve el channel_id cacheado para un handle desde Supabase."""
    try:
        res = sb.table("youtube_handles").select("channel_id").eq("handle", handle).execute()
        return res.data[0]["channel_id"] if res.data else None
    except Exception:
        return None


def cache_channel_id(handle: str, channel_id: str):
    """Guarda en Supabase la relación handle → channel_id."""
    try:
        sb.table("youtube_handles").upsert({
            "handle": handle,
            "channel_id": channel_id,
            "resolved_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass


async def resolve_handle(client: httpx.AsyncClient, handle: str) -> str | None:
    """
    Resuelve un @handle de YouTube a su channel_id UCxxxx.
    Funciona desde servidores fuera de la UE (sin bloqueo GDPR).
    Cachea el resultado en BD para no repetir la petición.
    """
    # Normalizar handle
    handle = handle.lstrip("@")
    cache_key = f"@{handle}"

    # Comprobar caché primero
    cached = get_cached_channel_id(cache_key)
    if cached:
        return cached

    url = f"https://www.youtube.com/@{handle}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = await client.get(url, headers=headers, timeout=15)
        html = r.text
        for pattern in [
            r'"channelId":"(UC[^"]{22})"',
            r'"externalId":"(UC[^"]{22})"',
        ]:
            m = re.search(pattern, html)
            if m:
                channel_id = m.group(1)
                cache_channel_id(cache_key, channel_id)
                log.info(f"Handle resuelto: @{handle} -> {channel_id}")
                return channel_id
    except Exception as e:
        log.warning(f"No se pudo resolver @{handle}: {e}")
    return None


def normalize_url(url: str) -> str:
    """Elimina parámetros de tracking para comparar URLs correctamente."""
    import urllib.parse
    try:
        parsed = urllib.parse.urlparse(url)
        # Quitar parámetros utm_* y similares
        params = urllib.parse.parse_qs(parsed.query)
        clean_params = {k: v for k, v in params.items()
                        if not k.startswith(("utm_", "ref", "source", "fbclid", "gclid"))}
        clean_query = urllib.parse.urlencode(clean_params, doseq=True)
        clean = parsed._replace(query=clean_query, fragment="")
        return urllib.parse.urlunparse(clean).rstrip("/")
    except Exception:
        return url.split("?")[0].rstrip("/")


def already_sent(url: str) -> bool:
    try:
        clean = normalize_url(url)
        res = sb.table("sent_items").select("url").eq("url", clean).execute()
        return bool(res.data)
    except Exception:
        return False


def mark_as_sent(url: str):
    try:
        clean = normalize_url(url)
        sb.table("sent_items").upsert({
            "url": clean,
            "sent_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# EXTRACCIÓN DE IMÁGENES
# ════════════════════════════════════════════════════════════════════════════

def get_youtube_video_id(url: str) -> str | None:
    """Extrae el video_id de cualquier URL de YouTube."""
    patterns = [
        r"youtube\.com/watch\?v=([^&\s]+)",
        r"youtu\.be/([^?\s]+)",
        r"youtube\.com/embed/([^?\s]+)",
        r"youtube\.com/v/([^?\s]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def get_youtube_thumbnail(url: str) -> str | None:
    """Devuelve la URL del thumbnail de mayor resolución de un video."""
    vid = get_youtube_video_id(url)
    if vid:
        return f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
    return None


async def extract_og_image(client: httpx.AsyncClient, url: str) -> str | None:
    """Intenta extraer la imagen Open Graph de un artículo."""
    if not url:
        return None
    try:
        headers = {"User-Agent": "TechDigestBot/2.0 (image extractor)"}
        r = await client.get(url, timeout=10, follow_redirects=True, headers=headers)
        html = r.text

        # og:image
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if m:
            return m.group(1)

        # twitter:image
        m = re.search(
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if m:
            return m.group(1)

    except Exception:
        pass
    return None


# ════════════════════════════════════════════════════════════════════════════
# TELEGRAM — ENVÍO VISUAL
# ════════════════════════════════════════════════════════════════════════════

def _inline_button(label: str, url: str) -> list:
    return [[{"text": label, "url": url}]]


async def _post_with_retry(client: httpx.AsyncClient, endpoint: str, payload: dict) -> dict:
    """POST a Telegram con retry automático si responde 429."""
    for attempt in range(3):
        r = await client.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=20)
        data = r.json()
        if data.get("ok"):
            return data
        retry_after = data.get("parameters", {}).get("retry_after", 0)
        if r.status_code == 429 and retry_after and attempt < 2:
            log.warning(f"Rate limit, esperando {retry_after}s...")
            await asyncio.sleep(retry_after + 1)
        else:
            return data
    return {}


async def send_photo_item(
    client: httpx.AsyncClient,
    image_url: str,
    caption: str,
    button_url: str,
    button_label: str,
):
    """Envía foto + caption + botón al canal."""
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML",
        "disable_notification": False,
        "reply_markup": {"inline_keyboard": _inline_button(button_label, button_url)},
    }
    data = await _post_with_retry(client, "sendPhoto", payload)

    if not data.get("ok"):
        log.warning(f"sendPhoto falló ({data.get('description')}), usando texto")
        await send_text_item(client, caption, button_url, button_label)
    else:
        log.info(f"Enviado con imagen: {button_url[:60]}")


async def send_text_item(
    client: httpx.AsyncClient,
    caption: str,
    button_url: str,
    button_label: str,
):
    """Envía mensaje de texto con botón (fallback sin imagen)."""
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
        "reply_markup": {"inline_keyboard": _inline_button(button_label, button_url)},
    }
    data = await _post_with_retry(client, "sendMessage", payload)
    if data.get("ok"):
        log.info(f"Enviado (texto): {button_url[:60]}")
    else:
        log.error(f"Error enviando: {str(data)[:200]}")


async def send_separator(client: httpx.AsyncClient):
    """Divisor visual entre lotes de noticias."""
    await client.post(
        f"{BASE_URL}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "━━━━━━━━━━━━━━━━━━━━━━\n🗞 <b>Novedades Tecnológicas</b>\n━━━━━━━━━━━━━━━━━━━━━━",
            "parse_mode": "HTML",
        },
        timeout=15,
    )


# ════════════════════════════════════════════════════════════════════════════
# PROCESADOR DE ITEMS
# ════════════════════════════════════════════════════════════════════════════

def clean_html(text: str) -> str:
    """Elimina etiquetas HTML del texto."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def escape_html(text: str) -> str:
    """Escapa caracteres especiales HTML para Telegram."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


# ════════════════════════════════════════════════════════════════════════════
# TRADUCCIÓN AL ESPAÑOL CON CLAUDE (por lotes)
# ════════════════════════════════════════════════════════════════════════════

async def translate_batch(client: httpx.AsyncClient, items: list[dict]) -> list[dict]:
    """Traduce items al español — SIEMPRE en español, con 3 reintentos."""
    if not GROQ_API_KEY:
        log.warning("Sin GROQ_API_KEY")
        for item in items:
            item["title_es"]   = item.get("title", "")
            item["summary_es"] = clean_html(item.get("summary", ""))[:150]
        return items

    input_list = [
        {
            "i": i,
            "title": clean_html(item.get("title", ""))[:200],
            "summary": clean_html(item.get("summary", ""))[:300],
        }
        for i, item in enumerate(items)
    ]

    prompt = (
        "Translate ALL articles to SPANISH. Return ONLY a JSON array:\n"
        '[{"i":0,"title_es":"titulo en español","summary_es":"resumen en español"}]\n\n'
        "- title_es: maximo 80 caracteres, SOLO en español\n"
        "- summary_es: 1-2 frases, SOLO en español, maximo 150 caracteres\n"
        "- NUNCA dejes texto en ingles\n"
        "- Si ya esta en español, dejalo igual\n"
        f"Articulos: {json.dumps(input_list, ensure_ascii=False)}\n\n"
        "DEVUELVE SOLO EL JSON. NADA MAS."
    )

    models = ["mixtral-8x7b-32768", "llama-3.1-8b-instant", "gemma2-9b-it"]

    for attempt, model in enumerate(models):
        try:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.1,
                },
                timeout=30,
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()

            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                raise ValueError("Sin JSON")

            translations = json.loads(match.group())
            trans_map = {t["i"]: t for t in translations}

            ok = True
            for i, item in enumerate(items):
                t = trans_map.get(i, {})
                te = (t.get("title_es") or "").strip()
                se = (t.get("summary_es") or "").strip()
                if not te or not se:
                    ok = False
                    break
                item["title_es"]   = te[:80]
                item["summary_es"] = se[:150]

            if ok:
                log.info(f"Traducidos {len(items)} items con {model}")
                return items

        except Exception as e:
            log.warning(f"Modelo {model} falló: {str(e)[:80]}")
            if attempt < len(models) - 1:
                await asyncio.sleep(1)

    # Último recurso: traducir uno a uno con prompt mínimo
    log.error("Todos los modelos fallaron en lote — intentando uno a uno")
    for item in items:
        try:
            single_prompt = (
                f"Traduce al español este título y resumen. Responde SOLO JSON:\n"
                f'{{"title_es":"TITULO","summary_es":"RESUMEN"}}\n\n'
                f'Título: {item.get("title","")}\n'
                f'Resumen: {clean_html(item.get("summary",""))[:200]}'
            )
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": single_prompt}],
                    "max_tokens": 300,
                    "temperature": 0.1,
                },
                timeout=15,
            )
            raw = r.json()["choices"][0]["message"]["content"].strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                t = json.loads(m.group())
                item["title_es"]   = t.get("title_es", "")[:80] or item.get("title", "")[:80]
                item["summary_es"] = t.get("summary_es", "")[:150] or clean_html(item.get("summary",""))[:150]
                continue
        except Exception:
            pass
        # Si todo falla, poner indicador de que está en otro idioma
        item["title_es"]   = f"[EN] {item.get('title','')[:76]}"
        item["summary_es"] = clean_html(item.get("summary", ""))[:150]
    return items


async def translate_all_items(
    client: httpx.AsyncClient, items: list[dict]
) -> list[dict]:
    """Traduce todos los items en lotes de TRANSLATE_BATCH."""
    translated = []
    for i in range(0, len(items), TRANSLATE_BATCH):
        batch = items[i : i + TRANSLATE_BATCH]
        batch = await translate_batch(client, batch)
        translated.extend(batch)
    return translated


# ════════════════════════════════════════════════════════════════════════════
# CAPTION
# ════════════════════════════════════════════════════════════════════════════

def build_caption(item: dict) -> str:
    """Construye el caption HTML del item con contenido en español y URL visible."""
    emoji   = CAT_EMOJI.get(item.get("category", "default"), "📰")
    title   = escape_html(item.get("title_es") or clean_html(item.get("title", "Sin título")))[:120]
    source  = escape_html(item.get("source", ""))
    summary = escape_html(item.get("summary_es") or clean_html(item.get("summary", "")))[:280]
    url     = item.get("url", "")

    if summary and not summary.endswith((".", "?", "!")):
        summary += "…"

    caption  = f"{emoji} <b>{title}</b>\n\n"
    if summary:
        caption += f"{summary}\n\n"
    caption += f"📍 <i>{source}</i>\n"
    if url:
        caption += f"🔗 {url}"
    return caption


async def process_item(client: httpx.AsyncClient, item: dict):
    """Decide si el item es video o artículo y lo envía visualmente."""
    url = item.get("url", "")
    if not url or already_sent(url):
        return

    caption     = build_caption(item)
    is_youtube  = "youtube.com" in url or "youtu.be" in url
    category    = item.get("category", "default")

    if is_youtube:
        # ── VIDEO YouTube ────────────────────────────────────────────────
        thumbnail = get_youtube_thumbnail(url)
        if not thumbnail:
            thumbnail = FALLBACK_IMAGES["youtube"]
        await send_photo_item(
            client,
            image_url=thumbnail,
            caption=caption,
            button_url=url,
            button_label="▶️ Ver Video",
        )
    else:
        # ── ARTÍCULO / NOTICIA ───────────────────────────────────────────
        og_image = await extract_og_image(client, url)
        image_url = og_image or FALLBACK_IMAGES.get(category, FALLBACK_IMAGES["default"])
        await send_photo_item(
            client,
            image_url=image_url,
            caption=caption,
            button_url=url,
            button_label="🔗 Leer Artículo",
        )

    mark_as_sent(url)
    await asyncio.sleep(DELAY_BETWEEN_MSGS)


# ════════════════════════════════════════════════════════════════════════════
# FETCH DE FUENTES
# ════════════════════════════════════════════════════════════════════════════

async def fetch_rss(
    client: httpx.AsyncClient, name: str, url: str, category: str
) -> list[dict]:
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        items = []
        for entry in feed.entries[:MAX_ITEMS]:
            items.append({
                "source":   name,
                "title":    entry.get("title", "Sin título"),
                "url":      entry.get("link", ""),
                "summary":  entry.get("summary", entry.get("description", ""))[:400],
                "category": category,
            })
        log.info(f"RSS [{name}]: {len(items)} items")
        return items
    except Exception as e:
        log.warning(f"RSS [{name}] falló: {e}")
        return []


async def fetch_hackernews(client: httpx.AsyncClient, top_n: int = 15) -> list[dict]:
    try:
        r = await client.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=REQUEST_TIMEOUT,
        )
        ids = r.json()[:top_n]

        async def get_item(item_id):
            try:
                resp = await client.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                    timeout=REQUEST_TIMEOUT,
                )
                return resp.json()
            except Exception:
                return None

        stories = await asyncio.gather(*[get_item(i) for i in ids])
        items = []
        for s in stories:
            if s and s.get("type") == "story" and s.get("url"):
                items.append({
                    "source":   "Hacker News",
                    "title":    s.get("title", ""),
                    "url":      s.get("url", ""),
                    "summary":  f"🔥 {s.get('score', 0)} puntos · {s.get('descendants', 0)} comentarios",
                    "category": "dev",
                })
        log.info(f"HackerNews: {len(items)} stories")
        return items
    except Exception as e:
        log.warning(f"HackerNews falló: {e}")
        return []


async def fetch_youtube_channel(
    client: httpx.AsyncClient, name: str, channel_id: str = "", handle: str = ""
) -> list[dict]:
    """Soporta channel_id directo o @handle (se resuelve automáticamente)."""
    # Resolver handle si no hay channel_id
    if not channel_id and handle:
        channel_id = await resolve_handle(client, handle)
        if not channel_id:
            log.warning(f"No se pudo obtener channel_id para {name} ({handle})")
            return []

    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    items = await fetch_rss(client, f"🎥 {name}", url, "youtube")
    return items[:3]


async def collect_visual_news(sources: dict) -> list[dict]:
    """Recopila todos los items de las fuentes activas."""
    headers = {
        "User-Agent": "TechDigestBot/2.0",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = []

        # RSS feeds
        for feed in sources.get("rss_feeds", []):
            category = feed.get("tags", ["default"])[0] if feed.get("tags") else "default"
            tasks.append(fetch_rss(client, feed["name"], feed["url"], category))

        # Hacker News
        hn = sources.get("hackernews", {})
        if hn.get("enabled", True):
            tasks.append(fetch_hackernews(client, hn.get("top_n", 15)))

        # YouTube — soporta channel_id directo o handle @nombre
        for ch in sources.get("youtube_channels", []):
            channel_id = ch.get("channel_id", "")
            handle     = ch.get("handle", "")
            tasks.append(fetch_youtube_channel(client, ch["name"], channel_id, handle))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)

    # Filtrar items sin URL y duplicados
    seen_urls = set()
    unique_items = []
    for item in all_items:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_items.append(item)

    log.info(f"Total items únicos: {len(unique_items)}")
    return unique_items


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

async def main():
    log.info("=== Visual News Bot iniciando ===")

    init_sent_db()

    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        sources = yaml.safe_load(f)

    all_items = await collect_visual_news(sources)

    # Filtrar solo los no enviados y limitar al máximo por ejecución
    new_items = [item for item in all_items if not already_sent(item.get("url", ""))]
    log.info(f"Items nuevos encontrados: {len(new_items)}")

    if len(new_items) > MAX_ITEMS_PER_RUN:
        log.info(f"Limitando a {MAX_ITEMS_PER_RUN} items (máx por ejecución)")
        new_items = new_items[:MAX_ITEMS_PER_RUN]

    if not new_items:
        log.info("Sin novedades. No se envía nada.")
        return

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Traducir todos los items al español en lotes
        log.info("Traduciendo items al español...")
        new_items = await translate_all_items(client, new_items)

        # Separador visual solo si hay contenido
        await send_separator(client)
        await asyncio.sleep(1)

        sent_count = 0
        for item in new_items:
            try:
                await process_item(client, item)
                sent_count += 1
            except Exception as e:
                log.error(f"Error procesando item: {e}")
                continue

    log.info(f"=== Enviados {sent_count} items al canal ===")


if __name__ == "__main__":
    asyncio.run(main())
