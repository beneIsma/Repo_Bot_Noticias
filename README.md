# Tech Digest Bot 🤖

Bot personal que recopila noticias de programación, IA, tecnología y robótica,
las filtra con Claude y te envía un resumen diario por Telegram.

## Stack

- **Python 3.11** — script principal
- **GitHub Actions** — scheduler gratuito (cron diario)
- **Claude API (Anthropic)** — motor cognitivo
- **Telegram Bot API** — canal de entrega

---

## Instalación paso a paso

### 1. Crea tu bot de Telegram

1. Abre Telegram y habla con [@BotFather](https://t.me/BotFather)
2. Escribe `/newbot` y sigue las instrucciones
3. Copia el **token** que te da (formato: `123456:ABC-DEF...`)
4. Para obtener tu **Chat ID**:
   - Manda cualquier mensaje a tu bot
   - Abre en el navegador:
     `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
   - Busca el campo `"id"` dentro de `"chat"` — ese es tu Chat ID

### 2. Obtén tu API Key de Anthropic

Ve a [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key

### 3. Sube el proyecto a GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/TU_USUARIO/tech-digest-bot.git
git push -u origin main
```

### 4. Configura los secretos en GitHub

Ve a tu repo → **Settings → Secrets and variables → Actions → New repository secret**

Crea estos tres secretos:

| Nombre | Valor |
|--------|-------|
| `ANTHROPIC_API_KEY` | Tu API key de Anthropic |
| `TELEGRAM_BOT_TOKEN` | Token de @BotFather |
| `TELEGRAM_CHAT_ID` | Tu Chat ID numérico |

### 5. Ajusta la hora de envío

Edita `.github/workflows/daily.yml` y cambia el cron:

```yaml
# 07:00 Madrid invierno (UTC+1):
- cron: "0 6 * * *"

# 07:00 Madrid verano (UTC+2):
- cron: "0 5 * * *"

# Solo días laborables a las 08:00 UTC+1:
- cron: "0 7 * * 1-5"
```

### 6. Personaliza las fuentes

Edita `sources.yaml` — sin tocar el código puedes:
- Añadir o quitar feeds RSS
- Cambiar cuántos artículos de HN recuperar
- Añadir canales de YouTube por `channel_id`
- Activar subreddits

### 7. Prueba manual

Desde GitHub Actions → **Run workflow** → podrás ver los logs y recibir el digest al instante.

---

## Estructura del proyecto

```
tech-digest-bot/
├── bot.py              # Script principal
├── sources.yaml        # Fuentes configurables (sin tocar código)
├── requirements.txt    # Dependencias Python
└── .github/
    └── workflows/
        └── daily.yml   # Scheduler de GitHub Actions
```

---

## Coste estimado

Con el uso diario típico (~50-80 artículos, ~15k tokens de entrada):

| Componente | Coste |
|---|---|
| GitHub Actions | Gratis (2000 min/mes) |
| Telegram Bot API | Gratis |
| Claude (claude-sonnet-4) | ~$0.02–0.05 por ejecución |
| **Total mensual** | **~$0.60–1.50/mes** |

---

## Solución de problemas

**El bot envía el mensaje sin formato (texto plano)**
→ Claude generó caracteres Markdown sin escapar. El bot los reenvía automáticamente en texto plano como fallback. Es normal ocasionalmente.

**Error `TELEGRAM_CHAT_ID` inválido**
→ Asegúrate de que el Chat ID es un número (puede ser negativo para grupos).

**No llegan artículos de alguna fuente**
→ Algunos feeds RSS cambian de URL. Verifica la URL directamente en el navegador.
→ Nitter suele estar caído; la sección de Twitter está comentada por defecto.
=======
# Repo_Bot_Noticias