"""
Tech Digest Bot v2.2 — Visual Format with Real Article Images
Flujo: sources.yaml → Fetch APIs/RSS → Claude API → Real Images → Telegram
"""

import os
import logging
import asyncio
import re
from datetime import datetime, timezone

import httpx
import feedparser
import yaml

def load_env_file():
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env_file()

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Constantes ─────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_ITEMS_PER_SOURCE = 10
MAX_INPUT_CHARS = 80_000
REQUEST_TIMEOUT = 15
SOURCES_FILE = "sources.yaml"

# ─── System Prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """TECH DIGEST BOT — FORMATO LIMPIO Y ESTRUCTURADO

TU ROL: Editor senior de tecnología. Curador de noticias impactantes.

CRITERIOS DE INCLUSIÓN:
• Dev: Frameworks revolucionarios, CVEs críticos, librerías con 10k+ stars
• Videos YouTube: Contenido educativo de calidad, tutorials, análisis técnico
• Tech: Noticias de tecnología relevante, actualizaciones importantes

CRITERIOS DE RECHAZO:
• Noticias >1 semana sin breaking news
• Predicciones sin datos
• Clickbait u opiniones vagas
• Duplicados (si 3 fuentes cubren lo mismo, solo 1)

FORMATO DE SALIDA EXACTO:

🔔 NOTICIAS — {DÍA}, {FECHA}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[NOTICIA_INICIO]
#1 TITULO DE LA NOTICIA (máx 60 caracteres, atractivo)
Descripción en 1-2 líneas: QUÉ pasó y POR QUÉ IMPORTA
👥 Nombre Fuente
https://url-exacta-de-la-noticia
[NOTICIA_FIN]

[NOTICIA_INICIO]
#2 OTRO TITULO NOTICIA
Descripción en 1-2 líneas breve
👥 Nombre Fuente
https://url-exacta
[NOTICIA_FIN]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 Compilado automáticamente · {N} fuentes analizadas
"""

def load_sources(filename: str) -> dict:
    """Carga configuración de fuentes desde YAML."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        log.warning(f"{filename} no encontrado. Usando configuración vacía.")
        return {}

# ════════════════════════════════════════════════════════════════════════════
# RECOPILACIÓN DE NOTICIAS
# ════════════════════════════════════════════════════════════════════════════

async def fetch_rss(
    client: httpx.AsyncClient, name: str, url: str
) -> list[dict]:
    """Obtiene artículos de un feed RSS."""
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        items = []
        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
            # Extraer imagen si está disponible
            image_url = None
            if hasattr(entry, 'media_content') and entry.media_content:
                image_url = entry.media_content[0].get('url')
            elif hasattr(entry, 'image'):
                image_url = entry.image.get('href')

            items.append({
                "source": name,
                "title": entry.get("title", "")[:100],
                "url": entry.get("link", ""),
                "summary": entry.get("summary", "")[:300],
                "image_url": image_url,
            })
        log.info(f"RSS [{name}]: {len(items)} artículos")
        return items
    except Exception as e:
        log.warning(f"RSS [{name}] falló: {e}")
        return []

async def fetch_youtube_channels(
    client: httpx.AsyncClient, channels: list[dict]
) -> list[dict]:
    """Obtiene últimos vídeos de canales de YouTube via RSS."""
    items = []
    for ch in channels:
        if "channel_id" not in ch:
            continue
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['channel_id']}"
        result = await fetch_rss(client, f"YouTube: {ch['name']}", url)
        # Para YouTube, extraer video_id y crear URL de thumbnail
        for item in result[:3]:
            match = re.search(r'v=([a-zA-Z0-9_-]+)', item['url'])
            if match:
                video_id = match.group(1)
                item['image_url'] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
            items.append(item)
    return items

async def collect_all_news(sources: dict) -> list[dict]:
    """Recopila noticias de todas las fuentes configuradas en paralelo."""
    headers = {
        "User-Agent": "TechDigestBot/2.2 (personal use)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = []
        for feed in sources.get("rss_feeds", []):
            tasks.append(fetch_rss(client, feed["name"], feed["url"]))
        if sources.get("youtube_channels"):
            tasks.append(fetch_youtube_channels(client, sources["youtube_channels"]))
        results = await asyncio.gather(*tasks)

    all_items = [item for sublist in results for item in sublist]
    log.info(f"Total artículos recopilados: {len(all_items)}")
    return all_items

# ════════════════════════════════════════════════════════════════════════════
# PROCESAMIENTO CON CLAUDE
# ════════════════════════════════════════════════════════════════════════════

def build_user_message(articles: list[dict]) -> str:
    """Formatea artículos en bruto para Claude."""
    today = datetime.now(timezone.utc).strftime("%A, %d %B %Y")
    lines = [
        f"FECHA DE HOY: {today}",
        f"TOTAL DE ARTÍCULOS A PROCESAR: {len(articles)}",
        "",
        "═" * 50,
        "ARTÍCULOS EN BRUTO:",
        "═" * 50,
        "",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"[{i}] FUENTE: {a['source']}")
        lines.append(f"    TÍTULO: {a['title']}")
        lines.append(f"    URL: {a['url']}")
        if a.get("summary"):
            lines.append(f"    RESUMEN: {a['summary'][:300]}")
        lines.append("")

    text = "\n".join(lines)
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS] + "\n\n[...contenido truncado]"
    return text

async def call_groq(user_message: str) -> str:
    """Genera el digest usando Groq API (gratuito)."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "max_tokens": 2048,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        digest = data["choices"][0]["message"]["content"]
        input_tokens = data.get("usage", {}).get("prompt_tokens", 0)
        output_tokens = data.get("usage", {}).get("completion_tokens", 0)
        log.info(f"Groq: {input_tokens} entrada, {output_tokens} salida tokens")
        return digest

# ════════════════════════════════════════════════════════════════════════════
# MAPEO ARTICULOS → IMAGENES
# ════════════════════════════════════════════════════════════════════════════

def parse_articles(digest: str, all_articles: list[dict]) -> list[dict]:
    """Parsea digest y asocia imágenes reales de los artículos."""
    articles = []
    pattern = r'\[NOTICIA_INICIO\](.*?)\[NOTICIA_FIN\]'
    matches = re.findall(pattern, digest, re.DOTALL)

    for match in matches:
        lines = [l.strip() for l in match.strip().split('\n') if l.strip()]
        if len(lines) < 4:
            continue

        titulo = lines[0].replace('#1 ', '').replace('#2 ', '').replace('#3 ', '').replace('#4 ', '').replace('#5 ', '').strip()
        descripcion = lines[1] if len(lines) > 1 else ""
        fuente = lines[2].replace('👥 ', '').strip() if len(lines) > 2 else "Unknown"
        url = lines[3] if len(lines) > 3 else ""

        # Buscar imagen asociada en los artículos originales
        image_url = None
        for a in all_articles:
            if url == a.get('url') and a.get('image_url'):
                image_url = a['image_url']
                break

        articles.append({
            "titulo": titulo[:60],
            "descripcion": descripcion[:100],
            "fuente": fuente,
            "url": url,
            "image_url": image_url,
        })

    return articles

# ════════════════════════════════════════════════════════════════════════════
# ENVÍO A TELEGRAM
# ════════════════════════════════════════════════════════════════════════════

async def send_telegram_visual(digest: str, all_articles: list[dict]) -> None:
    """Envía cada noticia: imagen real + título + descripción + URL directa."""
    articles = parse_articles(digest, all_articles)
    log.info(f"Enviando {len(articles)} noticias...")

    url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    url_message = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Emoji de tipo según fuente
    def source_emoji(fuente: str) -> str:
        if "YouTube" in fuente:
            return "🎬"
        return "📰"

    async with httpx.AsyncClient() as client:
        for i, art in enumerate(articles, 1):
            emoji = source_emoji(art['fuente'])

            # Texto: título, descripción, fuente, URL directa (sin HTML links)
            texto = (
                f"{emoji} {art['titulo']}\n\n"
                f"{art['descripcion']}\n\n"
                f"📍 {emoji} {art['fuente']}\n"
                f"🔗 {art['url']}"
            )

            if art.get('image_url'):
                # Enviar imagen con el texto como caption
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "photo": art['image_url'],
                    "caption": texto,
                }
                r = await client.post(url_photo, json=payload, timeout=15)
                if r.status_code == 200:
                    log.info(f"Noticia #{i} enviada con imagen")
                else:
                    # Si la imagen falla, enviar solo texto con preview de URL
                    log.warning(f"Noticia #{i} imagen falló, enviando texto")
                    payload = {
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": texto,
                        "disable_web_page_preview": False,
                    }
                    await client.post(url_message, json=payload, timeout=15)
            else:
                # Sin imagen: enviar texto; Telegram genera preview desde la URL
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": texto,
                    "disable_web_page_preview": False,
                }
                r = await client.post(url_message, json=payload, timeout=15)
                if r.status_code == 200:
                    log.info(f"Noticia #{i} enviada con preview de URL")
                else:
                    log.warning(f"Noticia #{i} falló: {r.json().get('description', '')}")

            await asyncio.sleep(3.0)

# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    """Flujo principal del bot."""
    log.info("━━━ Tech Digest Bot v2.2 (Imágenes Reales) iniciando ━━━")

    if not all([GROQ_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        log.error("Faltan variables de entorno")
        return

    sources = load_sources(SOURCES_FILE)
    log.info(f"Fuentes cargadas desde {SOURCES_FILE}")

    articles = await collect_all_news(sources)
    if not articles:
        log.error("No se obtuvieron artículos. Abortando.")
        return

    log.info("Enviando artículos a Claude para procesamiento...")
    user_message = build_user_message(articles)
    digest = await call_groq(user_message)
    log.info(f"Digest generado: {len(digest)} caracteres")

    log.info("Enviando digest a Telegram con imágenes reales...")
    await send_telegram_visual(digest, articles)
    log.info("━━━ Digest enviado con éxito ━━━")

if __name__ == "__main__":
    asyncio.run(main())
