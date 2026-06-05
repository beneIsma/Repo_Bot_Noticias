"""
Genera DOCUMENTACION.pdf a partir de DOCUMENTACION.md
"""

import sys
import io
import re
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

def md_to_pdf(md_path, pdf_path):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        print("Instalando reportlab...")
        os.system("pip install reportlab -q")
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()

    # Estilos personalizados
    h1 = ParagraphStyle("H1", parent=styles["Heading1"],
                        fontSize=20, textColor=colors.HexColor("#1a1a2e"),
                        spaceAfter=12, spaceBefore=20, leading=24)

    h2 = ParagraphStyle("H2", parent=styles["Heading2"],
                        fontSize=15, textColor=colors.HexColor("#16213e"),
                        spaceAfter=8, spaceBefore=16, leading=20,
                        borderPad=4)

    h3 = ParagraphStyle("H3", parent=styles["Heading3"],
                        fontSize=12, textColor=colors.HexColor("#0f3460"),
                        spaceAfter=6, spaceBefore=12, leading=16)

    body = ParagraphStyle("Body", parent=styles["Normal"],
                          fontSize=10, leading=15, spaceAfter=6,
                          textColor=colors.HexColor("#333333"))

    code = ParagraphStyle("Code", parent=styles["Code"],
                          fontSize=8, leading=12, backColor=colors.HexColor("#f4f4f4"),
                          leftIndent=12, rightIndent=12,
                          borderColor=colors.HexColor("#dddddd"),
                          borderWidth=0.5, borderPad=6)

    bullet = ParagraphStyle("Bullet", parent=body,
                             leftIndent=16, bulletIndent=8, spaceAfter=3)

    table_style = ParagraphStyle("Table", parent=body,
                                 fontSize=9, leftIndent=8)

    story = []

    lines = content.split("\n")
    in_code_block = False
    code_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Bloque de código
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lines = []
            else:
                in_code_block = False
                code_text = "\n".join(code_lines)
                story.append(Preformatted(code_text, code))
                story.append(Spacer(1, 6))
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Encabezados
        if line.startswith("# ") and not line.startswith("## "):
            text = line[2:].strip()
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            story.append(Paragraph(text, h1))
            story.append(HRFlowable(width="100%", thickness=2,
                                    color=colors.HexColor("#1a1a2e")))
            story.append(Spacer(1, 8))

        elif line.startswith("## "):
            text = line[3:].strip()
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            story.append(Spacer(1, 6))
            story.append(Paragraph(text, h2))
            story.append(HRFlowable(width="100%", thickness=1,
                                    color=colors.HexColor("#cccccc")))

        elif line.startswith("### "):
            text = line[4:].strip()
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            story.append(Paragraph(text, h3))

        # Separador ---
        elif line.strip() == "---":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="80%", thickness=0.5,
                                    color=colors.HexColor("#eeeeee")))
            story.append(Spacer(1, 4))

        # Tabla markdown (líneas con |)
        elif "|" in line and line.strip().startswith("|"):
            if not line.strip().startswith("|---"):
                cells = [c.strip() for c in line.split("|") if c.strip()]
                row_text = "  |  ".join(cells)
                row_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', row_text)
                story.append(Paragraph(row_text, table_style))

        # Listas con -
        elif line.strip().startswith("- ") or line.strip().startswith("* "):
            text = line.strip()[2:].strip()
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', text)
            story.append(Paragraph(f"• {text}", bullet))

        # Línea vacía
        elif line.strip() == "":
            story.append(Spacer(1, 4))

        # Párrafo normal
        else:
            text = line.strip()
            if not text:
                i += 1
                continue
            # Markdown básico
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
            text = re.sub(r'`(.*?)`', r'<font name="Courier" size="9">\1</font>', text)
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # Elimina links
            # Evita tags rotos
            try:
                story.append(Paragraph(text, body))
            except Exception:
                story.append(Paragraph(re.sub(r'<[^>]+>', '', text), body))

        i += 1

    doc.build(story)
    print(f"✅ PDF generado: {pdf_path}")


if __name__ == "__main__":
    md_to_pdf("DOCUMENTACION.md", "DOCUMENTACION.pdf")
