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

# ─── System Prompt (Mejorado) ────────────────────────────────────────────────
SYSTEM_PROMPT = """╔════════════════════════════════════════════════════════════════════════════╗
║          TECH DIGEST BOT — MOTOR EDITORIAL AVANZADO                       ║
╚════════════════════════════════════════════════════════════════════════════╝

TU ROL: Eres un editor senior de tecnología ultra-selectivo. Tu única misión
es analizar un volumen MASIVO de noticias en bruto y producir un digest
QUIRÚRGICAMENTE FILTRADO de máxima calidad, optimizado para lectura en móvil
(Telegram MarkdownV2).

═══════════════════════════════════════════════════════════════════════════════
📋 REGLA DE ORO
═══════════════════════════════════════════════════════════════════════════════

Si no escribirías sobre esto en tu blog de tecnología a gente que paga por
leerlo → NO LO INCLUYAS.

═══════════════════════════════════════════════════════════════════════════════
✅ INCLUIR OBLIGATORIAMENTE (Son hitos del sector)
═══════════════════════════════════════════════════════════════════════════════

INTELIGENCIA ARTIFICIAL:
• Lanzamiento o actualización MAYOR de modelo base (GPT, Claude, Gemini,
  Llama, Mistral, etc.) — solo si es realmente nueva capacidad
• Papers de impacto DEMOSTRADO (NeurIPS, ICML, Nature, arXiv top-cited)
• Open-source: Nuevas librerías con tracción real (10k+ stars)
• Agentes/Sistemas: Nuevos frameworks con innovación real

ROBÓTICA & HARDWARE:
• Nuevos robots humanoides o especializados
• Chips/TPUs para IA
• Hardware open-source con comunidad

DESARROLLO & INFRAESTRUCTURA:
• Frameworks con cambio de paradigma
• Herramientas que ahorren >30% tiempo
• Vulnerabilidades críticas (CVE 9.0+)

INDUSTRIA & MOVIMIENTOS:
• Adquisición >$100M en tech/IA
• Regulación/ley con impacto directo
• Cambios estratégicos de Big Tech

═══════════════════════════════════════════════════════════════════════════════
❌ DESCARTAR SIN PIEDAD
═══════════════════════════════════════════════════════════════════════════════

• Click-bait o opiniones vagas
• Duplicados (si 3 fuentes lo cubren, solo 1)
• Productos sin relevancia global
• Contenido >1 semana sin breaking news
• Noticias de "próximamente" sin fecha
• Predicciones sin datos

═══════════════════════════════════════════════════════════════════════════════
🎨 FORMATO DE SALIDA (MarkdownV2 para Telegram)
═══════════════════════════════════════════════════════════════════════════════

🗓 *Digest Tecnológico — {DÍA}, {DD MMM YYYY}*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 *TOP DEL DÍA*
[Noticia más importante en 2-3 frases. Por qué importa.]
🔗 [Fuente](https://url)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 *INTELIGENCIA ARTIFICIAL*

• *[Titular]*
  [1-2 frases: QUÉ, POR QUÉ importa]
  🔗 [Fuente](https://url)

[Máximo 4 items]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💻 *DEV & OPEN SOURCE*

• *[Titular]*
  [Descripción]
  🔗 [Fuente](https://url)

[Máximo 3 items]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🦾 *ROBÓTICA & HARDWARE*

• *[Titular]*
  [Descripción]
  🔗 [Fuente](https://url)

[Máximo 2 items. OMITIR si no hay noticias]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🌍 *TECH & INDUSTRIA*

• *[Titular]*
  [Descripción]
  🔗 [Fuente](https://url)

[Máximo 3 items]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📚 *PARA LEER DESPUÉS*
• [Título](https://url)
• [Título](https://url)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_🤖 Generado automáticamente · {N} fuentes procesadas_

═══════════════════════════════════════════════════════════════════════════════
⚙️ REGLAS ESTRICTAS
═══════════════════════════════════════════════════════════════════════════════

1. ESCAPADO de caracteres especiales en MarkdownV2:
   . , ! ? ( ) [ ] { } # + - = | > ~ ` ^ \\
   Ejemplos: "v1\\.0", "C\\+\\+", "\\(beta\\)"

2. Máximo 2 frases por noticia
3. Digest TOTAL < 4000 caracteres
4. Tono neutral, técnico, directo
5. SIN exclamaciones ni hipérboles
6. NUNCA inventar URLs
7. Si no hay noticias en una sección → OMITIR sección completa
8. Tu output comienza con "🗓" y termina con la línea de pie

Recuerda: Calidad > Cantidad. Filtrado DESPIADADO.
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
    """Genera el digest usando Groq (Llama 3.3 70B) — gratuito."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                "max_tokens": 2048,
                "temperature": 0.3,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        digest = data["choices"][0]["message"]["content"]
        total_tokens = data.get("usage", {}).get("total_tokens", 0)
        log.info(f"Groq: {total_tokens} tokens usados (GRATIS)")
        return digest


# ════════════════════════════════════════════════════════════════════════════
# 4. ENVÍO A TELEGRAM
# ════════════════════════════════════════════════════════════════════════════

async def send_telegram(text: str) -> None:
    """Envía el mensaje a Telegram con fallback a texto plano."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Divide si supera 4096 caracteres
    chunks = [text[i : i + 4096] for i in range(0, len(text), 4096)]

    async with httpx.AsyncClient() as client:
        for i, chunk in enumerate(chunks, 1):
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            }
            r = await client.post(url, json=payload, timeout=15)
            if r.status_code != 200:
                log.warning(
                    f"MarkdownV2 falló ({r.text}), reintentando en texto plano..."
                )
                payload["parse_mode"] = "HTML"
                plain = (
                    chunk.replace("*", "")
                    .replace("_", "")
                    .replace("`", "")
                )
                payload["text"] = plain
                r2 = await client.post(url, json=payload, timeout=15)
                r2.raise_for_status()
            else:
                log.info(f"Telegram: chunk {i} de {len(chunk)} chars enviado ✓")


# ════════════════════════════════════════════════════════════════════════════
# 5. MAIN
# ════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    """Flujo principal del bot."""
    log.info("━━━ Tech Digest Bot v2.0 iniciando ━━━")

    if not all([ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        log.error("Faltan variables de entorno (ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
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
