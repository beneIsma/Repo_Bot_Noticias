"""
Tech Digest Bot v3.0 — Pipeline con Subagentes
Flujo: sources.yaml → Fetch → Curator (Claude) → Writer (Claude) → Telegram
"""

import os
import logging
import asyncio
import re
import json
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_ITEMS_PER_SOURCE = 10
MAX_INPUT_CHARS = 60_000
REQUEST_TIMEOUT = 15
SOURCES_FILE = "sources.yaml"

# ─── Prompt Subagente 1: Curador ─────────────────────────────────────────────
CURATOR_PROMPT = """You are the Expert Content Curator for a Telegram channel for Developers and AI Engineers. Filter incoming articles ruthlessly.

CONTENT PILLARS: CODE, AI, INFRA, INNOVATION

REJECT:
- Marketing hype without technical depth
- Clickbait without verifiable benchmarks
- Duplicate news (keep only the most authoritative source)
- Vague opinions or predictions without data
- Articles older than 1 week

APPROVE only content with real technical value.

For each APPROVED article output JSON:
{
  "status": "APPROVED",
  "data": {
    "title": "Clean technical headline under 80 chars",
    "pillar": "CODE|AI|INFRA|INNOVATION",
    "tags": ["#Tag1", "#Tag2"],
    "summary": "Sentence 1: what it is. Sentence 2: why it matters to developers.",
    "url": "original url",
    "source": "source name"
  }
}

For REJECTED:
{"status": "REJECTED", "reason": "brief reason"}

Return a JSON array with one object per article. No text outside the JSON array.
Select maximum 6 best articles from the batch.
"""

# ─── Prompt Subagente 2: Writer ──────────────────────────────────────────────
WRITER_PROMPT = """You are a Senior Content Writer for a Telegram channel for developers. Transform the JSON article into a formatted Telegram post.

FORMAT RULES:
- Header: emoji + pillar + bold title
  💻 PROGRAMACIÓN: *Title*
  🤖 INTELIGENCIA ARTIFICIAL: *Title*
  ☁️ IT & INFRAESTRUCTURA: *Title*
  🚀 INNOVACIÓN TECH: *Title*
- Body: 2 short paragraphs from the summary, bold 3 key technical concepts
- Footer: 🔗 URL directly (no hyperlink text, just the raw URL)
- Hashtags: 3-4 relevant tags at the end

IMPORTANT:
- Return ONLY the post text, nothing else
- No greetings, no explanations
- Use Telegram-compatible markdown (bold with *, no HTML)
- Keep total length under 900 characters
"""

def load_sources(filename: str) -> dict:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        log.warning(f"{filename} no encontrado.")
        return {}

# ════════════════════════════════════════════════════════════════════════════
# RECOPILACIÓN
# ════════════════════════════════════════════════════════════════════════════

async def fetch_rss(client, name, url):
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        items = []
        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
            image_url = None
            if hasattr(entry, 'media_content') and entry.media_content:
                image_url = entry.media_content[0].get('url')
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

async def fetch_youtube_channels(client, channels):
    items = []
    for ch in channels:
        if "channel_id" not in ch:
            continue
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['channel_id']}"
        result = await fetch_rss(client, f"YouTube: {ch['name']}", url)
        for item in result[:3]:
            match = re.search(r'v=([a-zA-Z0-9_-]+)', item['url'])
            if match:
                item['image_url'] = f"https://img.youtube.com/vi/{match.group(1)}/maxresdefault.jpg"
            items.append(item)
    return items

async def collect_all_news(sources):
    headers = {"User-Agent": "TechDigestBot/3.0", "Accept": "application/rss+xml, */*"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = [fetch_rss(client, f["name"], f["url"]) for f in sources.get("rss_feeds", [])]
        if sources.get("youtube_channels"):
            tasks.append(fetch_youtube_channels(client, sources["youtube_channels"]))
        results = await asyncio.gather(*tasks)
    all_items = [item for sub in results for item in sub]
    log.info(f"Total artículos recopilados: {len(all_items)}")
    return all_items

# ════════════════════════════════════════════════════════════════════════════
# LLAMADAS A CLAUDE
# ════════════════════════════════════════════════════════════════════════════

async def call_claude(system_prompt: str, user_message: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
                "temperature": 0.3,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        tokens_in = data.get("usage", {}).get("input_tokens", 0)
        tokens_out = data.get("usage", {}).get("output_tokens", 0)
        log.info(f"Claude: {tokens_in} entrada, {tokens_out} salida tokens")
        return data["content"][0]["text"]

# ════════════════════════════════════════════════════════════════════════════
# SUBAGENTE 1: CURADOR
# ════════════════════════════════════════════════════════════════════════════

async def curate_articles(articles: list) -> list:
    """Filtra y selecciona los mejores artículos via Claude."""
    today = datetime.now(timezone.utc).strftime("%A, %d %B %Y")
    lines = [f"DATE: {today}\n"]
    for i, a in enumerate(articles, 1):
        lines.append(f"[{i}] SOURCE: {a['source']}")
        lines.append(f"    TITLE: {a['title']}")
        lines.append(f"    URL: {a['url']}")
        if a.get("summary"):
            lines.append(f"    SUMMARY: {a['summary'][:200]}")
        lines.append("")

    user_msg = "\n".join(lines)
    if len(user_msg) > MAX_INPUT_CHARS:
        user_msg = user_msg[:MAX_INPUT_CHARS]

    log.info("Subagente 1: Curando artículos...")
    raw = await call_claude(CURATOR_PROMPT, user_msg)

    # Extraer JSON del response
    try:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            curated = json.loads(match.group(0))
        else:
            curated = json.loads(raw)
    except Exception as e:
        log.error(f"Error parseando JSON del curador: {e}")
        log.debug(f"Raw response: {raw[:500]}")
        return []

    approved = [a for a in curated if a.get("status") == "APPROVED"]
    log.info(f"Curador: {len(approved)} artículos aprobados de {len(curated)} procesados")
    return approved

# ════════════════════════════════════════════════════════════════════════════
# SUBAGENTE 2: WRITER
# ════════════════════════════════════════════════════════════════════════════

async def write_post(article: dict) -> str:
    """Formatea un artículo aprobado como post de Telegram."""
    user_msg = json.dumps(article["data"], ensure_ascii=False, indent=2)
    log.info(f"Subagente 2: Formateando '{article['data']['title'][:50]}'...")
    post = await call_claude(WRITER_PROMPT, user_msg)
    return post.strip()

# ════════════════════════════════════════════════════════════════════════════
# ENVÍO A TELEGRAM
# ════════════════════════════════════════════════════════════════════════════

async def send_post(client, article: dict, post_text: str, all_articles: list):
    """Envía imagen (si existe) + post formateado a Telegram."""
    url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    url_message = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    article_url = article["data"].get("url", "")

    # Buscar imagen en los artículos originales
    image_url = None
    for a in all_articles:
        if a.get("url") == article_url and a.get("image_url"):
            image_url = a["image_url"]
            break

    if image_url:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": image_url,
            "caption": post_text[:1024],
        }
        r = await client.post(url_photo, json=payload, timeout=15)
        if r.status_code == 200:
            log.info(f"Enviado con imagen: {article['data']['title'][:50]}")
            return
        log.warning(f"Imagen falló, enviando texto: {r.json().get('description', '')}")

    # Sin imagen o si falló: enviar texto con preview de URL
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": post_text,
        "disable_web_page_preview": False,
    }
    r = await client.post(url_message, json=payload, timeout=15)
    if r.status_code == 200:
        log.info(f"Enviado como texto: {article['data']['title'][:50]}")
    else:
        log.warning(f"Falló: {r.json().get('description', '')}")

# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

async def main():
    log.info("━━━ Tech Digest Bot v3.0 (Pipeline Subagentes) iniciando ━━━")

    if not all([ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        log.error("Faltan variables: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        return

    # 1. Recopilar noticias
    sources = load_sources(SOURCES_FILE)
    all_articles = await collect_all_news(sources)
    if not all_articles:
        log.error("Sin artículos. Abortando.")
        return

    # 2. Subagente 1: Curador — filtra y selecciona
    curated = await curate_articles(all_articles)
    if not curated:
        log.error("Ningún artículo aprobado por el curador.")
        return

    # 3. Subagente 2 + Envío — formatea y envía cada artículo
    log.info(f"Enviando {len(curated)} artículos a Telegram...")
    async with httpx.AsyncClient() as client:
        for article in curated:
            post_text = await write_post(article)
            await send_post(client, article, post_text, all_articles)
            await asyncio.sleep(3.0)

    log.info("━━━ Pipeline completado con éxito ━━━")

if __name__ == "__main__":
    asyncio.run(main())
