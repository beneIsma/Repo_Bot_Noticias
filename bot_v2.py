"""
Tech Digest Bot v2.0 — Motor principal mejorado
Flujo: sources.yaml → Fetch APIs/RSS → Claude API → Telegram
"""

import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
import feedparser
import yaml

# Cargar variables desde .env si existen
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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_ITEMS_PER_SOURCE = 10
MAX_INPUT_CHARS = 80_000
REQUEST_TIMEOUT = 15
SOURCES_FILE = "sources.yaml"

# ─── System Prompt (Formato Visual) ─────────────────────────────────────────
SYSTEM_PROMPT = """TECH DIGEST BOT — FORMATO VISUAL Y LLAMATIVO

TU ROL: Editor senior de tecnología. Genera un digest VISUAL, LLAMATIVO y FÁCIL DE LEER.

CRITERIOS DE INCLUSIÓN:
• Dev: Frameworks revolucionarios, CVEs críticos, librerías con 10k+ stars
• Videos YouTube: Contenido educativo de calidad, tutorials, análisis técnico
• Tech: Noticias de tecnología relevante, actualizaciones importantes

CRITERIOS DE RECHAZO:
• Noticias >1 semana sin breaking news
• Predicciones sin datos
• Clickbait u opiniones vagas
• Duplicados (si 3 fuentes cubren lo mismo, solo 1)
• Productos sin relevancia global

FORMATO DE SALIDA (TEXTO VISUAL PURO):
═════════════════════════════════════════════════════════════════════════════

🔔 TECH DIGEST — {DÍA}, {FECHA}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 TOP DEL DÍA #1

📰 TITULO DE LA NOTICIA (máx 10 palabras, atractivo)

Descripción: QUÉ pasó + POR QUÉ IMPORTA en 1-2 frases cortas.

[SI ES VIDEO YOUTUBE: incluir 🎬 VIDEO]
👥 Fuente: [Nombre]
🔗 https://url-exacta-de-la-noticia

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💻 DESARROLLO & OPEN SOURCE

🔹 #2 TITULO NOTICIA

Breve descripción de QUÉ + POR QUÉ IMPORTA (1-2 líneas max)

[SI ES VIDEO: 🎬 VIDEO]
👥 Fuente: [Nombre]
🔗 https://url-exacta

[Máximo 5 noticias por sección]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📚 PARA LEER DESPUÉS

📖 Título 1 → https://url-1
📖 Título 2 → https://url-2
📖 Título 3 → https://url-3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Compilado automáticamente · {N} fuentes analizadas

═════════════════════════════════════════════════════════════════════════════

INSTRUCCIONES CRÍTICAS:

1. NO USAR HTML — solo texto plano con emojis y líneas
2. Títulos: CORTOS (máx 10 palabras), ATRACTIVOS
3. Descripción: QUÉ + POR QUÉ IMPORTA en 1-2 líneas
4. URLs: EXACTAMENTE como están en el input, NUNCA inventar
5. VIDEOS YOUTUBE: Marca con 🎬 VIDEO cuando sea de YouTube
6. Emojis: Usa números (#1, #2, #3...) para orden visual
7. Total: < 3500 caracteres para caber en 2 mensajes
8. Orden: TOP primero, luego por importancia
9. Secciones vacías: OMITIR completamente
10. Tono: Profesional, técnico, directo, SIN exclamaciones

MÁXIMA PRIORIDAD: Calidad > Cantidad. Filtra DESPIADADAMENTE por impacto.
"""


# ════════════════════════════════════════════════════════════════════════════
# 1. CARGA DE FUENTES
# ════════════════════════════════════════════════════════════════════════════

def load_sources(path: str = SOURCES_FILE) -> dict:
    """Carga la configuración de fuentes desde YAML."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        log.error(f"Archivo {path} no encontrado")
        return {}


# ════════════════════════════════════════════════════════════════════════════
# 2. FETCH DE CONTENIDO
# ════════════════════════════════════════════════════════════════════════════

async def fetch_rss(
    client: httpx.AsyncClient, name: str, url: str
) -> list[dict]:
    """Parsea un feed RSS/Atom y devuelve lista de artículos."""
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        feed = feedparser.parse(r.text)
        items = []
        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
            items.append(
                {
                    "source": name,
                    "title": entry.get("title", "Sin título"),
                    "url": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", ""))[
                        :500
                    ],
                }
            )
        log.info(f"RSS [{name}]: {len(items)} artículos")
        return items
    except Exception as e:
        log.warning(f"RSS [{name}] falló: {e}")
        return []


async def fetch_hackernews(
    client: httpx.AsyncClient, top_n: int = 20
) -> list[dict]:
    """Obtiene los top stories de Hacker News."""
    try:
        r = await client.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=REQUEST_TIMEOUT,
        )
        ids = r.json()[:top_n]

        async def get_item(item_id: int) -> dict | None:
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
                items.append(
                    {
                        "source": "Hacker News",
                        "title": s.get("title", ""),
                        "url": s.get("url", f"https://news.ycombinator.com/item?id={s['id']}"),
                        "summary": f"Score: {s.get('score', 0)} puntos, {s.get('descendants', 0)} comentarios",
                    }
                )
        log.info(f"HackerNews: {len(items)} stories")
        return items
    except Exception as e:
        log.warning(f"HackerNews falló: {e}")
        return []


async def fetch_devto(
    client: httpx.AsyncClient, tags: list[str], per_page: int = 10
) -> list[dict]:
    """Obtiene artículos de Dev.to filtrados por tags."""
    items = []
    for tag in tags:
        try:
            r = await client.get(
                f"https://dev.to/api/articles?tag={tag}&per_page={per_page}&top=1",
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            for article in r.json():
                items.append(
                    {
                        "source": f"Dev.to #{tag}",
                        "title": article.get("title", ""),
                        "url": article.get("url", ""),
                        "summary": article.get("description", "")[:400],
                    }
                )
        except Exception as e:
            log.warning(f"Dev.to [{tag}] falló: {e}")
    log.info(f"Dev.to: {len(items)} artículos")
    return items


async def fetch_reddit(
    client: httpx.AsyncClient, subreddits: list[dict]
) -> list[dict]:
    """Obtiene posts hot de subreddits via RSS público."""
    items = []
    for sub in subreddits:
        name = sub["name"]
        url = f"https://www.reddit.com/r/{name}/hot/.rss?limit={MAX_ITEMS_PER_SOURCE}"
        result = await fetch_rss(client, f"r/{name}", url)
        items.extend(result)
    return items


async def fetch_youtube_channels(
    client: httpx.AsyncClient, channels: list[dict]
) -> list[dict]:
    """Obtiene últimos vídeos de canales de YouTube via RSS."""
    items = []
    for ch in channels:
        # Solo procesar canales con channel_id configurado
        if "channel_id" not in ch:
            log.debug(f"YouTube [{ch['name']}]: Sin channel_id, saltando")
            continue
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['channel_id']}"
        result = await fetch_rss(client, f"YouTube: {ch['name']}", url)
        items.extend(result[:3])
    return items


async def collect_all_news(sources: dict) -> list[dict]:
    """Recopila noticias de todas las fuentes configuradas en paralelo."""
    headers = {
        "User-Agent": "TechDigestBot/2.0 (personal use)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = []

        # RSS Feeds
        for feed in sources.get("rss_feeds", []):
            tasks.append(fetch_rss(client, feed["name"], feed["url"]))

        # Hacker News
        hn = sources.get("hackernews", {})
        if hn.get("enabled", True):
            tasks.append(fetch_hackernews(client, hn.get("top_n", 20)))

        # Dev.to
        devto = sources.get("devto", {})
        if devto:
            tasks.append(
                fetch_devto(client, devto.get("tags", []), devto.get("per_page", 10))
            )

        # Reddit
        if sources.get("reddit_subreddits"):
            tasks.append(fetch_reddit(client, sources["reddit_subreddits"]))

        # YouTube
        if sources.get("youtube_channels"):
            tasks.append(fetch_youtube_channels(client, sources["youtube_channels"]))

        results = await asyncio.gather(*tasks)

    all_items = [item for sublist in results for item in sublist]
    log.info(f"Total artículos recopilados: {len(all_items)}")
    return all_items


# ════════════════════════════════════════════════════════════════════════════
# 3. PROCESAMIENTO CON CLAUDE
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
        text = text[:MAX_INPUT_CHARS] + "\n\n[...contenido truncado por límite de tokens]"
    return text


async def call_claude(user_message: str) -> str:
    """Genera el digest usando Claude API (Anthropic)."""
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
                "max_tokens": 2048,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        digest = data["content"][0]["text"]
        input_tokens = data.get("usage", {}).get("input_tokens", 0)
        output_tokens = data.get("usage", {}).get("output_tokens", 0)
        log.info(f"Claude: {input_tokens} entrada, {output_tokens} salida tokens")
        return digest


# ════════════════════════════════════════════════════════════════════════════
# 4. ENVÍO A TELEGRAM
# ════════════════════════════════════════════════════════════════════════════

async def send_telegram(text: str) -> None:
    """Envía el mensaje a Telegram con formato HTML, fallback a texto plano."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Divide si supera 4096 caracteres
    chunks = [text[i : i + 4096] for i in range(0, len(text), 4096)]

    async with httpx.AsyncClient() as client:
        for i, chunk in enumerate(chunks, 1):
            # Primer intento: HTML
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
            r = await client.post(url, json=payload, timeout=15)

            if r.status_code != 200:
                # Fallback a texto plano
                log.warning(f"HTML falló ({r.json().get('description', 'Error')}), reintentando en texto plano...")
                import re
                plain = chunk
                plain = re.sub(r'<[^>]+>', '', plain)  # Remover todas las etiquetas HTML

                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": plain,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                }
                r2 = await client.post(url, json=payload, timeout=15)
                if r2.status_code == 200:
                    log.info(f"Telegram: chunk {i} de {len(plain)} chars enviado (TEXTO PLANO)")
                else:
                    log.error(f"Telegram: chunk {i} falló incluso en texto plano")
                    r2.raise_for_status()
            else:
                log.info(f"Telegram: chunk {i} de {len(chunk)} chars enviado OK (HTML)")


# ════════════════════════════════════════════════════════════════════════════
# 5. MAIN
# ════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    """Flujo principal del bot."""
    log.info("━━━ Tech Digest Bot v2.0 iniciando ━━━")

    if not all([ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        log.error("Faltan variables de entorno: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        return

    # 1. Cargar fuentes
    sources = load_sources(SOURCES_FILE)
    log.info(f"Fuentes cargadas desde {SOURCES_FILE}")

    # 2. Recopilar noticias
    articles = await collect_all_news(sources)
    if not articles:
        log.error("No se obtuvieron artículos. Abortando.")
        return

    # 3. Construir prompt y llamar a Claude
    log.info("Enviando artículos a Claude para procesamiento...")
    user_message = build_user_message(articles)
    digest = await call_claude(user_message)
    log.info(f"Digest generado: {len(digest)} caracteres")

    # 4. Enviar a Telegram
    log.info("Enviando digest a Telegram...")
    await send_telegram(digest)
    log.info("━━━ Digest enviado con éxito ━━━")


if __name__ == "__main__":
    asyncio.run(main())
