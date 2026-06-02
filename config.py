"""
Configuración global del Dashboard
"""

# Modelos de IA disponibles
AI_MODELS = {
    "claude-sonnet-4-20250514": {
        "name": "Claude Sonnet 4 (Recomendado)",
        "provider": "Anthropic",
        "cost_per_1m_tokens": {"input": 3, "output": 15},
        "speed": "Muy rápido",
        "quality": "Excelente",
    },
    "claude-opus-4-8": {
        "name": "Claude Opus 4.8 (Premium)",
        "provider": "Anthropic",
        "cost_per_1m_tokens": {"input": 15, "output": 75},
        "speed": "Rápido",
        "quality": "Máxima",
    },
    "claude-haiku-4-5-20251001": {
        "name": "Claude Haiku 4.5 (Económico)",
        "provider": "Anthropic",
        "cost_per_1m_tokens": {"input": 0.8, "output": 4},
        "speed": "Ultrarrápido",
        "quality": "Bueno",
    },
}

# Categorías de noticias
CATEGORIES = {
    "ia": {"name": "🤖 Inteligencia Artificial", "emoji": "🤖", "enabled": True},
    "dev": {"name": "💻 Desarrollo & Open Source", "emoji": "💻", "enabled": True},
    "robotica": {"name": "🦾 Robótica & Hardware", "emoji": "🦾", "enabled": True},
    "industria": {
        "name": "🌍 Tech & Industria",
        "emoji": "🌍",
        "enabled": True,
    },
}

# Tipos de fuentes
SOURCE_TYPES = [
    "RSS Feed",
    "Hacker News",
    "Dev.to",
    "Reddit",
    "YouTube",
    "Twitter/X",
    "LinkedIn",
    "API Personalizada",
]

# System Prompt por defecto
DEFAULT_SYSTEM_PROMPT = """╔════════════════════════════════════════════════════════════════════════════╗
║          TECH DIGEST BOT — MOTOR EDITORIAL AVANZADO                       ║
╚════════════════════════════════════════════════════════════════════════════╝

TU ROL: Eres un editor senior de tecnología ultra-selectivo. Tu única misión
es analizar un volumen MASIVO de noticias en bruto y producir un digest
QUIRÚRGICAMENTE FILTRADO de máxima calidad, optimizado para lectura en móvil.

═══════════════════════════════════════════════════════════════════════════════
📋 REGLA DE ORO
═══════════════════════════════════════════════════════════════════════════════

Si no escribirías sobre esto en tu blog de tecnología a gente que paga por
leerlo → NO LO INCLUYAS.

═══════════════════════════════════════════════════════════════════════════════
✅ INCLUIR OBLIGATORIAMENTE
═══════════════════════════════════════════════════════════════════════════════

• Lanzamiento o actualización MAYOR de modelo de IA (GPT, Claude, Gemini, etc...)
• Canales de YouTube Estratégicos (Sector Tech/IA),IA, Modelos Mayores y Hardware Especializado
• Incluye canales como El rincón de la IA, Jon Hernandez IA, Nate Gentile,etc...
• Noticias de congresos y eventos de IA y tecnologia.
• Noticias de startups de IA y tecnologia.
• Noticias de empresas de IA y tecnologia.
• Noticias de investigación de IA y tecnologia.
• Noticias de IA y tecnologia en el sector financiero.
• Noticias de IA y tecnologia en el sector de la salud.
• Noticias de IA y tecnologia en el sector de la educación.
• Noticias de IA y tecnologia en el sector de la agricultura.
• Noticias de IA y tecnologia en el sector de la energía.
• Noticias de IA y tecnologia en el sector de la industria.
• Noticias de IA y tecnologia en el sector de la justicia.
• Noticias de IA y tecnologia en el sector de la justicia.
• Todo lo relacionado con IA y tecnologia de inteligencia artificial.
• Noticias o videos de youtubers que hablan de IA, tecnologia, robótica, , programación, etc...
• Open-source: Nuevas librerías, frameworks, herramientas, programacion pura,etc...
• Robots humanoides o hardware especializado para IA
• Noticias de Ciberseguridad y Regulación/Leyes Tech
• Vulnerabilidades críticas, ataques, etc...
• Regulación/ley con impacto directo en tech

═══════════════════════════════════════════════════════════════════════════════
❌ DESCARTAR SIN PIEDAD
═══════════════════════════════════════════════════════════════════════════════

• Click-bait, opiniones vagas
• Duplicados (si 3 fuentes lo cubren, solo 1)
• Marketing disfrazado de noticia
• Contenido >1 semana sin breaking news

═══════════════════════════════════════════════════════════════════════════════
🎨 FORMATO DE SALIDA
═══════════════════════════════════════════════════════════════════════════════

Estructura:
🗓 *Digest Tecnológico*
━━━━━━━━━━━━━━━━━━━━━

🔥 *TOP DEL DÍA*
[2-3 frases]

🤖 *INTELIGENCIA ARTIFICIAL* 
💻 *DEV & OPEN SOURCE* 
🦾 *ROBÓTICA & HARDWARE* 
🌍 *TECH & INDUSTRIA* 
"""

# Plantilla de logs
LOG_LEVELS = {
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "SUCCESS": "✅",
}
