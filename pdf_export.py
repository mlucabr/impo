from __future__ import annotations

import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def _money(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: float) -> str:
    return f"{v:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def build_pdf_report(official, inputs_dict: dict, result, taxes_df, memory_df) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.4*cm, rightMargin=1.4*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Assistente de Importação — Memória de Cálculo", styles["Title"]))
    story.append(Paragraph("Relatório gerado automaticamente em Streamlit", styles["Normal"]))
    story.append(Spacer(1, 0.4*cm))

    summary_data = [
        ["NCM", official.ncm],
        ["Descrição", official.description or ""],
        ["País de origem", inputs_dict.get("country_of_origin", "")],
        ["Porto origem", inputs_dict.get("port_origin", "")],
        ["Porto destino", inputs_dict.get("port_destination", "")],
        ["UF destino", inputs_dict.get("uf_destination", "")],
        ["INCOTERM", inputs_dict.get("incoterm", "")],
        ["Quantidade", str(inputs_dict.get("quantity", ""))],
        ["Unidade", inputs_dict.get("unit", "")],
        ["Moeda mercadoria", inputs_dict.get("product_currency", "")],
        ["Moeda frete", inputs_dict.get("freight_currency", "")],
    ]
    t_summary = Table(summary_data, colWidths=[4.2*cm, 12.6*cm])
    t_summary.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("Resumo executivo", styles["Heading2"]))
    kpis = [
        ["Valor aduaneiro", _money(result.customs_value_brl)],
        ["Total landed cost", _money(result.total_landed_cost_brl)],
        ["Custo unitário (BRL)", _money(result.unit_landed_cost_brl)],
        [f"Custo unitário ({inputs_dict.get('product_currency','')})", f"{result.unit_landed_cost_foreign:,.4f}"],
        ["Share tributos", _pct(result.tax_share_pct)],
        ["Share logística", _pct(result.logistics_share_pct)],
        ["Fator de importação", f"{result.import_factor:,.4f}"],
    ]
    t_kpi = Table(kpis, colWidths=[6.0*cm, 4.8*cm])
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("Tributos", styles["Heading2"]))
    tax_data = [["Tributo", "Alíquota", "Valor (BRL)"]]
    for _, row in taxes_df.iterrows():
        tax_data.append([row["Tributo"], _pct(float(row["Alíquota (%)"])), _money(float(row["Valor (BRL)"]))])
    t_tax = Table(tax_data, colWidths=[4.0*cm, 3.2*cm, 4.0*cm])
    t_tax.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))
    story.append(t_tax)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("Memória de cálculo", styles["Heading2"]))
    mem_data = [["Etapa", "Valor (BRL)"]]
    for _, row in memory_df.iterrows():
        mem_data.append([row["Etapa"], _money(float(row["Valor (BRL)"]))])
    t_mem = Table(mem_data, colWidths=[9.0*cm, 4.0*cm])
    t_mem.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1d4ed8")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 8),
    ]))
    story.append(t_mem)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
