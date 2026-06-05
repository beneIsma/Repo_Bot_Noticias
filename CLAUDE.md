# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tech Digest Bot v2.2** — Un agregador de noticias que recopila artículos de 13 fuentes RSS y 13 canales YouTube, los filtra usando Claude API, y entrega noticias curadas vía Telegram cada hora con imágenes reales.

Propósito: Entrega automática de noticias tecnológicas de impacto, visualmente atractivas, sin ruido.

## Architecture

### Data Flow

```
AUTOMATIZADO (Cada hora vía GitHub Actions):

sources.yaml (13 RSS + 13 YouTube)
    ↓
[bot_v2.py] → Recopila 156+ artículos
    ├─ RSS feeds: Xataka, El País, GitHub, The Verge, etc.
    └─ YouTube: midudev, Lex Fridman, Two Minute Papers, etc.
    ↓
[Artículos JSON] — {source, title, url, summary, image_url}
    ↓
[Claude API - haiku-4-5] → Filtra a 5-8 noticias impactantes
    ↓
[send_telegram_visual] → Envía cada noticia:
    • Imagen real (si disponible)
    • Título + Descripción + Fuente + Link (en caption)
    ↓
Telegram chat (cada hora, ~10 segundos)
```

### Core Modules

- **bot_v2.py** — Script principal (orquesta recolección, filtrado y envío)
  - `load_sources()` — Lee sources.yaml
  - `fetch_rss()` — Obtiene feeds RSS + extrae imágenes si están disponibles
  - `fetch_youtube_channels()` — Obtiene vídeos YouTube + genera URLs de thumbnails
  - `collect_all_news()` — Recopila en paralelo con asyncio.gather()
  - `build_user_message()` — Formatea para Claude
  - `call_claude()` — Claude API (modelo: haiku-4-5, temperature: 0.3)
  - `parse_articles()` — Parsea output de Claude, mapea a imágenes originales
  - `send_telegram_visual()` — Envía imagen + caption (1 noticia = 1 mensaje)

- **sources.yaml** — Configuración declarativa (no tocar código)
  - `rss_feeds`: 13 feeds (Xataka, GitHub, The Verge, etc.)
  - `youtube_channels`: 13 canales (midudev, Lex Fridman, DotCSV, etc.)
  - Cada entrada: {name, url/channel_id, tags}

- **.github/workflows/daily.yml** — GitHub Actions (ejecución horaria)
  - `cron: "0 * * * *"` — Cada hora UTC
  - Inyecta: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  - Timeout: 10 minutos

## Key Design Decisions

### 1. Claude como Editor Editorial

El sistema prompt (SYSTEM_PROMPT en bot.py, ~140 líneas) codifica las reglas editoriales:
- Criterios de inclusión obligatoria (lanzamientos de IA, papers impactantes, vulnerabilidades críticas, etc.)
- Criterios de rechazo (opinions vagas, repeticiones, marketing)
- Formato de salida exacto (MarkdownV2 con escaping de caracteres especiales)
- Límites: máx 4 items por sección, máx 4000 caracteres totales, máx 2 frases por noticia

**Implicación:** Cambios editoriales requieren modificar SYSTEM_PROMPT. Cambios en estructura de salida requieren actualizar regex o parsers en send_telegram.

### 2. Configuración sin Código

`sources.yaml` permite:
- Añadir/quitar fuentes RSS sin tocar bot.py
- Ajustar número de artículos por fuente (MAX_ITEMS_PER_SOURCE en bot.py = límite duro)
- Activar/desactivar fuentes (ej: hackernews.enabled)

**No incluye:** filtros de palabras clave, pesos por fuente, deduplicación de artículos similares → todo delegado a Claude.

### 3. Truncado por Tokens

MAX_INPUT_CHARS (80_000) limita el texto enviado a Claude para controlar costes. Si se recopilan >100 artículos, solo los primeros ~500 caracteres se envían.

**Implicación:** En días con muchas noticias, algunos artículos se descartan silenciosamente. Ver logs para diagnosticar.

### 4. Fallback en MarkdownV2

Si Telegram rechaza MarkdownV2 (caracteres sin escapar), el bot reintenta en texto plano (remove * _ `). Normal ocasionalmente.

## Common Development Tasks

### 1. Prueba Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Establecer variables de entorno (Windows PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:TELEGRAM_BOT_TOKEN = "123456:ABC-..."
$env:TELEGRAM_CHAT_ID = "12345678"

# O en Bash
export ANTHROPIC_API_KEY="sk-ant-..."
export TELEGRAM_BOT_TOKEN="123456:ABC-..."
export TELEGRAM_CHAT_ID="12345678"

# Ejecutar
python bot.py
```

Ver logs en consola (INFO level por defecto).

### 2. Debugging de Fuentes

- Si una fuente falla: verificar URL directamente en navegador
- Reddit/YouTube: feed RSS aún funciona aunque la web sea diferente
- Nitter (Twitter): mirrors inestables; comentar sección si falla
- Dev.to: requiere tags válidos en sources.yaml

Ver logs: "RSS [nombre]: X artículos" indica éxito; "RSS [nombre] falló" indica error.

### 3. Ajustar Prompt Editorial

Modificar SYSTEM_PROMPT en bot.py (líneas 34-139):
- Cambiar criterios INCLUIR OBLIGATORIAMENTE / DESCARTAR SIN PIEDAD
- Cambiar estructura de salida (secciones, orden, máx items)
- Cambiar tono (neutral → sensacionalista, etc.)

**Atención:** El escape de caracteres MarkdownV2 es crítico. Claude genera correctamente si el prompt es claro.

### 4. Añadir Nueva Fuente

Tres opciones:

**A. RSS simples:** Añadir a sources.yaml bajo `rss_feeds`
```yaml
- name: "Mi Feed"
  url: "https://ejemplo.com/feed.xml"
```

**B. APIs nuevas:** Implementar `fetch_* ()` en bot.py
- Seguir patrón de `fetch_devto()` o `fetch_reddit()`
- Retornar `list[dict]` con keys {source, title, url, summary}
- Añadir llamada en `collect_all_news()`

**C. Modificaciones en sources.yaml:** Editar el YAML sin tocar código.

### 5. Testing de Telegram Parsing

Si cambias el formato MarkdownV2:
1. Generar un digest de prueba localmente
2. Copiar output de Claude
3. Pastearlo en un script pequeño que llame a send_telegram()
4. Verificar que Telegram lo renderiza correctamente

### 6. Optimizar Costes

- Reducir `top_n` en Hacker News (línea 66 en sources.yaml)
- Reducir `per_page` en Dev.to (línea 77 en sources.yaml)
- Reducir `MAX_INPUT_CHARS` en bot.py (línea 30) — pero perderás artículos
- Cambiar CLAUDE_MODEL a `claude-haiku-4-5` si necesitas <$0.01/ejecución (menos calidad)

## Configuration Reference

### Environment Variables (Requeridas)

- `ANTHROPIC_API_KEY` — API key de Anthropic Console
- `TELEGRAM_BOT_TOKEN` — Token de @BotFather en Telegram
- `TELEGRAM_CHAT_ID` — Chat ID numérico (obtener via `getUpdates`)

### Constants en bot.py

| Constante | Línea | Propósito |
|-----------|-------|----------|
| `CLAUDE_MODEL` | 28 | Versión de Claude (actual: claude-sonnet-4) |
| `MAX_ITEMS_PER_SOURCE` | 29 | Límite de artículos a recuperar por fuente |
| `MAX_INPUT_CHARS` | 30 | Truncado de entrada a Claude para controlar costes |
| `REQUEST_TIMEOUT` | 31 | Timeout en segundos para HTTP requests |
| `SYSTEM_PROMPT` | 35–139 | Criterios editoriales y formato de salida |

### GitHub Actions (daily.yml)

- `cron: "0 6 * * *"` — Hora UTC (6 UTC = 7 CET invierno)
- Cambiar a `"0 5 * * *"` para verano (8 CET)
- `timeout-minutes: 10` — Límite de tiempo del job

## Data Structures

### Article Dictionary

Cada artículo en `collect_all_news()` es:
```python
{
    "source": str,       # Nombre de la fuente (ej: "Hacker News")
    "title": str,        # Título del artículo
    "url": str,          # URL (puede estar vacía en algunos casos)
    "summary": str       # Resumen o descripción (max 500 chars)
}
```

### Sources Config (sources.yaml)

```yaml
rss_feeds:
  - name: str
    url: str

hackernews:
  enabled: bool
  top_n: int

devto:
  tags: list[str]
  per_page: int

reddit_subreddits:
  - name: str

youtube_channels:
  - name: str
    channel_id: str
```

## Logging

Nivel: INFO (ver bot.py línea 17)

Mensajes clave:
- `RSS [nombre]: X artículos` — Feed procesado correctamente
- `HackerNews: X stories` — Top stories obtenidas
- `Total artículos recopilados: X` — Resumen de recopilación
- `Claude: X tokens entrada, Y tokens salida` — Consumption API
- `Telegram: chunk de X chars enviado correctamente` — Envío exitoso

Errores:
- `[WARNING] RSS [nombre] falló: ...` — Error al parsear feed
- `[ERROR] No se obtuvieron artículos. Abortando.` — Critical: sin contenido

## Cost Estimation

Uso típico (~50-80 artículos/día, ~15k tokens entrada):
- Claude (claude-sonnet-4): ~$0.02–0.05/ejecución
- GitHub Actions: $0 (2000 min/mes gratis)
- Telegram Bot API: $0 (gratis)
- **Total mensual:** ~$0.60–1.50

Con claude-haiku: ~$0.001–0.003/ejecución → ~$0.03–0.10/mes

## Troubleshooting

### "El bot envía sin formato (texto plano)"
→ Claude generó caracteres Markdown sin escapar. Fallback a texto plano es normal ocasionalmente.

### "TELEGRAM_CHAT_ID inválido"
→ Chat ID debe ser número (puede ser negativo para grupos). Verificar con `getUpdates`.

### "No llegan artículos de alguna fuente"
→ Feed RSS cambió URL. Verificar directamente en navegador.
→ Nitter inestable; comentar sección Twitter.

### "Max input chars warning"
→ Demasiados artículos recopilados. Bajar `top_n`/`per_page` en sources.yaml.
