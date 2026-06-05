# Guía de Subagentes — Tech Digest Bot

## Arquitectura Rediseñada

```
FLUJO AUTOMATIZADO (Cada hora vía GitHub Actions)

[bot_v2.py] Recolecta artículos
    ↓
    [Artículos en JSON]
    ↓
[TÚ en Claude Code] Invocas los subagentes
    ├─ content-curator-telegram ✓ Filtra/desuplica
    ├─ tech-translator-es ✓ Traduce (si es necesario)
    ├─ telegram-content-writer ✓ Formatea MarkdownV2
    └─ Resultado final listo para Telegram
```

---

## Workflow Diario

### Paso 1: Bot Recolecta Noticias (Automático)
**Cuándo:** Cada hora (GitHub Actions, cron: `0 * * * *`)  
**Qué hace:** 
- Recopila artículos de todas las fuentes en sources.yaml
- Los guarda en memoria
- Los envía a Anthropic Claude API

**Output esperado:** Digest formateado en MarkdownV2 → Telegram

---

### Paso 2: Tú Controlas los Subagentes (Manual desde Claude Code)

Si quieres **curación editorial avanzada**, tú invocas los subagentes:

#### **Opción A: Solo artículos crudos + Claude básico (Actual)**
```
Bot recolecta → Claude genera digest → Telegram
```
✅ Rápido  
❌ Sin filtrado manual

---

#### **Opción B: Pipeline completo con subagentes (Recomendado)**
```
Bot recolecta → [TÚ invocas aquí en Claude Code]
    ├─ content-curator-telegram (remover marketing, duplicados)
    ├─ telegram-content-writer (emojis, formato atractivo)
    └─ send_telegram() (envía)
```

**Cómo hacerlo:**

1. **Tú le dices a Claude Code:**
   ```
   "Curador estos 40 artículos del feed diario"
   ```

2. **Yo automáticamente:**
   - Invoco `content-curator-telegram` → artículos aprobados (15-20)
   - Invoco `telegram-content-writer` → post formateado
   - Te entrego el resultado

3. **Tú copias y pegas en Telegram** (o me pides que lo envíe)

---

## Subagentes Disponibles

### 1️⃣ **content-curator-telegram**
**Función:** Filtrar artículos según criterios editoriales

**Input:** Lista de artículos crudos (JSON)
```json
[
  {
    "source": "MIT Technology Review",
    "title": "Nueva técnica de RAG supera benchmarks",
    "url": "https://...",
    "summary": "..."
  },
  ...
]
```

**Output:** Solo artículos aprobados con metadata
```json
{
  "APPROVED": [
    {
      "source": "MIT Technology Review",
      "title": "Nueva técnica de RAG supera benchmarks",
      "category": "ai",
      "urgency": "high",
      "why": "Impacto demostrado en producción",
      ...
    }
  ],
  "REJECTED": [...],
  "STATS": {"approved": 12, "rejected": 28, "duplicates": 2}
}
```

**Cuándo usarlo:**
- Artículos crudos sin filtrar
- Sospechas de marketing/spam
- Quieres deduplicación inteligente

---

### 2️⃣ **telegram-content-writer**
**Función:** Formatea artículos aprobados en post Telegram atractivo

**Input:** Artículos aprobados del curator
```json
[
  {
    "source": "OpenAI Blog",
    "title": "GPT-5 Preview Released",
    "url": "https://...",
    "category": "ai",
    "summary": "..."
  }
]
```

**Output:** Post MarkdownV2 listo para copiar-pegar
```
📰 *DIGEST TECNOLÓGICO — 5 JUN 2026*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 *TOP DEL DÍA*
*GPT-5 Preview Released*
OpenAI anuncia la preview de GPT-5 con capacidades mejoradas de razonamiento y visión.
🔗 [Leer](https://...)

[...más items...]
```

**Cuándo usarlo:**
- Después de curar con curator
- Quieres emojis, títulos atractivos, estructura visual

---

### 3️⃣ **tech-translator-es**
**Función:** Traduce contenido técnico inglés → español

**Input:** Artículos o texto en inglés
```json
{
  "title": "Advances in Retrieval-Augmented Generation",
  "summary": "New RAG techniques improve LLM accuracy..."
}
```

**Output:** Mismo JSON pero traducido (mantiene términología técnica)
```json
{
  "title": "Avances en Generación Aumentada por Recuperación",
  "summary": "Nuevas técnicas de RAG mejoran la precisión de LLM..."
}
```

**Cuándo usarlo:**
- Artículos originales en inglés
- Quieres mantener terminología técnica

---

### 4️⃣ **weekly-digest-curator**
**Función:** Comprime 7 días (35+ artículos) en TOP 5

**Input:** Todos los artículos de lunes-sábado
```json
[
  {"source": "HN", "title": "...", "date": "2026-06-01", ...},
  {"source": "Xataka", "title": "...", "date": "2026-06-02", ...},
  ...
]
```

**Output:** Newsletter ultra-compacta (1 post Telegram)
```
📰 *TECH DIGEST #24 — TOP 5 DE LA SEMANA*

🥇 #1 OpenAI GPT-5 Preview...
🥈 #2 Google DeepMind AlphaFold 3...
🥉 #3 Meta Llama 3.5...
4️⃣ Microsoft Copilot+...
5️⃣ Anthropic Claude 4...

_35 artículos resumidos · 7 fuentes · 1 newsletter_
```

**Cuándo usarlo:**
- Es domingo (newsletter semanal)
- Tienes 35+ artículos acumulados

---

## Ejemplo: Tu Flujo Típico Hoy

### **Escenario 1: Automático (Sin intervención)**
```
12:00 UTC → Bot recolecta → Claude genera → Telegram envía
13:00 UTC → Bot recolecta → Claude genera → Telegram envía
...
```
✅ Fácil, sin trabajo manual

---

### **Escenario 2: Curación Manual (Recomendado)**

**Tú:**
```
"Curador estos artículos del feed de hoy"
[pasas lista de 40 artículos]
```

**Yo:**
```
[invoco content-curator-telegram]
→ 40 artículos → 15 aprobados ✓

[invoco telegram-content-writer]
→ 15 artículos → 1 post MarkdownV2 ✓

Resultado:
📰 *DIGEST — 5 JUN 2026*
[contenido formateado]
```

**Tú:**
```
Copias el resultado y lo pegas en Telegram
```

---

### **Escenario 3: Traducción + Curación**

**Tú:**
```
"Extrae las noticias en inglés, tradúcelas, curador y formatea todo"
```

**Yo:**
```
[busco artículos en inglés]
[invoco tech-translator-es]
[invoco content-curator-telegram]
[invoco telegram-content-writer]

Resultado: Post en español, curado y formateado ✓
```

---

## Cambios en Esta Versión

| Cambio | Antes | Ahora |
|--------|-------|-------|
| **Scheduling** | 30 minutos | Cada hora (cron: `0 * * * *`) |
| **API** | Groq (free) | Anthropic Claude |
| **YouTube** | 25 canales | +5 nuevos (Fazt, Rodrigo, Juan Gabriel, Webpositer, Eureka) |
| **Subagentes** | N/A | Disponibles en Claude Code |
| **Control editorial** | Solo Claude | Tú + subagentes |

---

## Nuevas Fuentes Añadidas

**YouTube (5 nuevos canales):**
- 🎓 Fazt Code (@FaztCode) — Programación
- 🎓 Rodrigo Olivares (@rodrigolivaresr) — IA/Dev
- 🎓 Juan Gabriel Gomila (@JuanGabrielGomila) — Data Science
- 🎙️ WebpositerPodcast (@WebpositerPodcast) — Desarrollo Web
- 🎓 Eureka Tutoriales (@EurekaTutoriales) — Programación

Todos en **sources.yaml**, sin cambios en el código.

---

## Próximos Pasos

**1. Verifica las credenciales:**
```bash
echo $env:ANTHROPIC_API_KEY  # PowerShell
echo $ANTHROPIC_API_KEY       # Bash
```

**2. Prueba el bot localmente:**
```bash
python bot_v2.py
```

**3. Cuando necesites curación avanzada, dime:**
```
"Curador y formatea los artículos de hoy para Telegram"
```

**4. Todos los domingos (para newsletter semanal):**
```
"Compila el newsletter semanal con los 7 últimos días"
```

---

## Soporte

Si algo falla:
- ❌ Bot no envía → Verifica ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- ❌ Artículos con HTML → Curator los limpia automáticamente
- ❌ Telegram rechaza MarkdownV2 → Writer añade fallback a HTML

¡Listo! Ahora tienes control total sobre el editorial. 🚀
