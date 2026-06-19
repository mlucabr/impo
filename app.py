from __future__ import annotations

import io
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from config_data import (
    get_icms_rate_by_uf,
    get_port_defaults,
    load_icms_defaults,
    load_port_defaults,
)
from official_data import get_official_rates, normalize_ncm
from pdf_export import build_pdf_report
from tax_engine import (
    ImportInputs,
    calculate_import_costs,
    executive_breakdown_dataframe,
    memory_dataframe,
    tax_dataframe,
)

st.set_page_config(page_title="OneSupply Impo", page_icon="🚢", layout="wide")

CUSTOM_CSS = """
<style>
.block-container {padding-top: 3.0rem; padding-bottom: 0.5rem;}
[data-testid="stMetricValue"] {font-size: 1.6rem;}
.kicker {font-size: 0.85rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em;}
.hero {padding: 0rem 1.1rem; border: 1px solid #e2e8f0; border-radius: 18px; background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);} 
.small-card {padding: 0.85rem 1rem; border: 1px solid #e2e8f0; border-radius: 16px; background: white;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float) -> str:
    return f"{v:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def num4(v: float) -> str:
    return f"{v:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_br_number(v: float, decimals: int = 2) -> str:
    try:
        return f"{float(v):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)


def style_brl_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    formatters = {}

    for col in df.columns:
        col_up = str(col).upper()

        # colunas monetárias / de custo / valor
        if "VALOR" in col_up or "CUSTO" in col_up:
            formatters[col] = lambda x: fmt_br_number(x, 2)

        # colunas de alíquota
        elif "ALÍQUOTA" in col_up or "ALIQ" in col_up or col_up.endswith("(%)"):
            formatters[col] = lambda x: fmt_br_number(x, 2)

    return df.style.format(formatters)

def init_state() -> None:
    if "icms_df" not in st.session_state:
        st.session_state.icms_df = load_icms_defaults()
    if "port_df" not in st.session_state:
        st.session_state.port_df = load_port_defaults()
    if "result_pack" not in st.session_state:
        st.session_state.result_pack = None


def make_excel_export(result, official, inputs_dict, taxes_df, memory_df, breakdown_df) -> bytes:
    resumo = pd.DataFrame([
        {"Campo": "NCM", "Valor": official.ncm},
        {"Campo": "Descrição NCM", "Valor": official.description or ""},
        {"Campo": "País de origem", "Valor": inputs_dict["country_of_origin"]},
        {"Campo": "Quantidade", "Valor": inputs_dict["quantity"]},
        {"Campo": "Unidade", "Valor": inputs_dict["unit"]},
        {"Campo": "Moeda mercadoria", "Valor": inputs_dict["product_currency"]},
        {"Campo": "Moeda frete", "Valor": inputs_dict["freight_currency"]},
        {"Campo": "INCOTERM", "Valor": inputs_dict["incoterm"]},
        {"Campo": "Porto origem", "Valor": inputs_dict["port_origin"]},
        {"Campo": "Porto destino", "Valor": inputs_dict["port_destination"]},
        {"Campo": "UF destino", "Valor": inputs_dict["uf_destination"]},
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        taxes_df.to_excel(writer, sheet_name="Tributos", index=False)
        memory_df.to_excel(writer, sheet_name="Memória", index=False)
        breakdown_df.to_excel(writer, sheet_name="Dashboard", index=False)
        st.session_state.icms_df.to_excel(writer, sheet_name="ICMS_UF", index=False)
        st.session_state.port_df.to_excel(writer, sheet_name="Portos", index=False)

        workbook = writer.book
        money_fmt = workbook.add_format({"num_format": 'R$ #,##0.00'})

        for ws_name in ["Memória", "Dashboard"]:
            ws = writer.sheets[ws_name]
            ws.set_column(0, 0, 28)
            ws.set_column(1, 2, 18, money_fmt)

        ws_t = writer.sheets["Tributos"]
        ws_t.set_column(0, 0, 18)
        ws_t.set_column(1, 1, 14)
        ws_t.set_column(2, 2, 18, money_fmt)

        writer.sheets["Resumo"].set_column("A:A", 28)
        writer.sheets["Resumo"].set_column("B:B", 42)
        writer.sheets["ICMS_UF"].set_column("A:C", 28)
        writer.sheets["Portos"].set_column("A:F", 28)

    output.seek(0)
    return output.getvalue()


def render_waterfall_chart(result) -> alt.Chart:
    df = pd.DataFrame(result.waterfall_rows)
    df = df[df["Valor"] != 0].copy()
    df["Acumulado"] = df["Valor"].cumsum()
    df["Base"] = df["Acumulado"] - df["Valor"]

    return alt.Chart(df).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Etapa:N", sort=None, title="Etapa"),
        y=alt.Y("Base:Q", title="Valor (BRL)", axis=alt.Axis(format=",.0f")),
        y2="Acumulado:Q",
        color=alt.Color("Grupo:N", legend=alt.Legend(title="Grupo")),
        tooltip=["Etapa", alt.Tooltip("Valor:Q", format=",.2f"), "Grupo"]
    ).properties(height=360)


def render_breakdown_chart(df: pd.DataFrame) -> alt.Chart:
    return alt.Chart(df).mark_bar(cornerRadius=5).encode(
        x=alt.X("Categoria:N", sort=None, title="Categoria"),
        y=alt.Y("Valor (BRL):Q", title="Valor (BRL)", axis=alt.Axis(format=",.0f")),
        color=alt.Color("Grupo:N", legend=None),
        tooltip=["Categoria", alt.Tooltip("Valor (BRL):Q", format=",.2f"), "Grupo"]
    ).properties(height=320)


init_state()

with st.sidebar:
    st.markdown("### Assistente de Importação")
    st.divider()
    pis_rate = st.number_input("PIS-Importação (%)", min_value=0.0, max_value=100.0, value=2.10, step=0.01, key="sb_pis_rate")
    cofins_rate = st.number_input("COFINS-Importação (%)", min_value=0.0, max_value=100.0, value=9.65, step=0.01, key="sb_cofins_rate")
    use_uf_icms = st.toggle("Usar tabela ICMS por UF", value=True, key="sb_use_uf_icms")
    include_afrmm = st.toggle("Aplicar AFRMM (25% longo curso)", value=True, key="sb_include_afrmm")
    st.divider()
    st.subheader("v2.1")
    st.caption("""
        - Tabelas de ICMS e custos-padrão podem ser editadas na aba Parâmetros.
        - País de origem incluído.
        - Premissas de custos por porto editáveis no app.
        - Exportação em Excel e PDF.
        - Dashboard executivo com composição e waterfall.        
        """)

st.markdown("<div class='hero'><h3 style='margin:0'>Simulação de Importação</h3></div>", unsafe_allow_html=True)
st.write("")
main_tab, dashboard_tab, params_tab, docs_tab = st.tabs(["Operação", "Dashboard Executivo", "Parâmetros", "Documentação"])

with main_tab:
    left, right = st.columns([1.45, 1])

    with left:
        with st.form("import_form_v2"):
            st.subheader("1) Dados da mercadoria")
            a1, a2, a3, a4, a5 = st.columns(5)
            quantity = a1.number_input("Quantidade", min_value=0.0001, value=1.0, step=1.0, key="frm_quantity")
            unit = a2.text_input("Unidade", value="KG", key="frm_unit")
            unit_price = a3.number_input("Valor unitário", min_value=0.0, value=0.0, step=0.01, key="frm_unit_price")
            product_currency = a4.text_input("Moeda da mercadoria", value="USD", key="frm_product_currency").upper()
            product_fx = a5.number_input(f"Câmbio {product_currency} → BRL", min_value=0.000001, value=5.40, step=0.0001, format="%.4f", key="frm_product_fx")

            b1, b2, b3 = st.columns([1.1, 1, 1])
            ncm = b1.text_input("NCM", value="", key="frm_ncm")
            country_of_origin = b2.text_input("País de origem", value="CN", key="frm_country_of_origin").upper()
            incoterm = b3.selectbox("INCOTERM", ["EXW", "FCA", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"], index=2, key="frm_incoterm")

            st.subheader("2) Logística internacional")
            c1, c2, c3, c4, c5 = st.columns(5)
            freight_value = c1.number_input("Frete marítimo", min_value=0.0, value=0.0, step=0.01, key="frm_freight_value")
            freight_currency = c2.text_input("Moeda do frete", value="USD", key="frm_freight_currency").upper()
            freight_fx = c3.number_input(f"Câmbio {freight_currency} → BRL", min_value=0.000001, value=5.40, step=0.0001, format="%.4f", key="frm_freight_fx")
            intl_insurance_pct = c4.number_input("Seguro internacional (%)", min_value=0.0, max_value=100.0, value=0.30, step=0.01, key="frm_intl_insurance_pct")
            port_origin = c5.text_input("Porto de origem", value="CNSHA", key="frm_port_origin")

            d1, d2, d3 = st.columns(3)
            port_destination = d1.text_input("Porto de destino (código)", value="PNG", key="frm_port_destination").upper()
            uf_list = sorted(st.session_state.icms_df["UF"].dropna().unique().tolist())
            uf_destination = d2.selectbox("UF destino", options=uf_list, index=uf_list.index("PR") if "PR" in uf_list else 0, key="frm_uf_destination")
            apply_port_templates = d3.toggle("Aplicar premissas do porto", value=True, key="frm_apply_port_templates")

            port_defaults = get_port_defaults(port_destination, st.session_state.port_df)

            st.subheader("3) Custos no Brasil")
            e1, e2, e3, e4 = st.columns(4)
            port_costs = e1.number_input(
                "Custos portuários (BRL)", min_value=0.0,
                value=float(port_defaults["CUSTO_PORTUARIO_BASE_BRL"] if apply_port_templates else 0.0), step=0.01,
                key="frm_port_costs"
            )
            customs_clearance = e2.number_input(
                "Custos de desembaraço (BRL)", min_value=0.0,
                value=float(port_defaults["DESEMBARACO_BASE_BRL"] if apply_port_templates else 0.0), step=0.01,
                key="frm_customs_clearance"
            )
            inland_freight = e3.number_input(
                "Frete porto → planta (BRL)", min_value=0.0,
                value=float(port_defaults["FRETE_PORTO_PLANTA_BASE_BRL"] if apply_port_templates else 0.0), step=0.01,
                key="frm_inland_freight"
            )
            inland_insurance_pct = e4.number_input(
                "Ad valorem (%)", min_value=0.0, max_value=100.0,
                value=float(port_defaults["SEGURO_NACIONAL_ADVAL_PCT"] if apply_port_templates else 0.15), step=0.01,
                key="frm_inland_insurance_pct"
            )

            submitted = st.form_submit_button("Calcular", type="primary")

    with right:
        port_defaults_preview = get_port_defaults(str(st.session_state.get("frm_port_destination", "PNG")), st.session_state.port_df)
        st.markdown("<div class='small-card'>", unsafe_allow_html=True)
        st.subheader("Premissas sugeridas:")
        st.write(f"**Porto destino:** {str(st.session_state.get('frm_port_destination', 'PNG')).upper()}")
        st.write(f"**Custos portuários base:** {brl(float(port_defaults_preview['CUSTO_PORTUARIO_BASE_BRL']))}")
        st.write(f"**Desembaraço base:** {brl(float(port_defaults_preview['DESEMBARACO_BASE_BRL']))}")
        st.write(f"**Frete porto → planta base:** {brl(float(port_defaults_preview['FRETE_PORTO_PLANTA_BASE_BRL']))}")
        st.write(f"**Seguro nacional base:** {pct(float(port_defaults_preview['SEGURO_NACIONAL_ADVAL_PCT']))}")
        st.caption(port_defaults_preview.get("OBS", ""))
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='small-card' style='margin-top:12px'>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        try:
            ncm_norm = normalize_ncm(ncm)
            if len(ncm_norm) != 8 or ncm_norm == "00000000":
                raise ValueError("Informe uma NCM válida com 8 dígitos.")

            official = get_official_rates(ncm_norm)
            if official.ii_rate is None:
                raise ValueError("Não foi possível localizar a alíquota de II para a NCM informada na base oficial.")
            if official.ipi_rate is None:
                raise ValueError("Não foi possível localizar a alíquota de IPI para a NCM informada na base oficial.")

            icms_rate = get_icms_rate_by_uf(uf_destination, st.session_state.icms_df) if use_uf_icms else 17.0

            inputs = ImportInputs(
                quantity=quantity,
                unit=unit,
                unit_price_foreign=unit_price,
                product_currency=product_currency,
                product_fx_to_brl=product_fx,
                freight_foreign=freight_value,
                freight_currency=freight_currency,
                freight_fx_to_brl=freight_fx,
                country_of_origin=country_of_origin,
                port_origin=port_origin,
                port_destination=port_destination,
                uf_destination=uf_destination,
                port_costs_brl=port_costs,
                customs_clearance_brl=customs_clearance,
                ncm=ncm_norm,
                incoterm=incoterm,
                intl_insurance_pct=intl_insurance_pct,
                inland_freight_brl=inland_freight,
                inland_insurance_pct=inland_insurance_pct,
                pis_rate=pis_rate,
                cofins_rate=cofins_rate,
                icms_rate=icms_rate,
                include_afrmm=include_afrmm,
            )
            result = calculate_import_costs(inputs, official.ii_rate, official.ipi_rate)
            taxes_df = tax_dataframe(result)
            memory_df = memory_dataframe(result)
            breakdown_df = executive_breakdown_dataframe(result)

            st.session_state.result_pack = {
                "official": official,
                "inputs": inputs,
                "result": result,
                "taxes_df": taxes_df,
                "memory_df": memory_df,
                "breakdown_df": breakdown_df,
            }

        except Exception as exc:
            st.error(f"Erro ao processar a operação: {exc}")

    if st.session_state.result_pack is not None:
        pack = st.session_state.result_pack
        official = pack["official"]
        inputs = pack["inputs"]
        result = pack["result"]
        taxes_df = pack["taxes_df"]
        memory_df = pack["memory_df"]
        breakdown_df = pack["breakdown_df"]

        st.divider()
        top1, top2, top3, top4, top5 = st.columns(5)
        top1.metric("NCM", official.ncm)
        top2.metric("II", pct(result.ii_rate))
        top3.metric("IPI", pct(result.ipi_rate))
        top4.metric("Valor aduaneiro", brl(result.customs_value_brl))
        top5.metric("Atualizado em", datetime.now().strftime("%d/%m/%Y %H:%M"))

        st.success(f"Descrição da NCM: {official.description or 'Descrição não encontrada na base pública.'}")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total landed cost", brl(result.total_landed_cost_brl))
        k2.metric(f"Custo unitário ({inputs.unit})", brl(result.unit_landed_cost_brl))
        k3.metric(f"Custo unitário ({inputs.product_currency})", num4(result.unit_landed_cost_foreign))
        k4.metric("Fator de importação", num4(result.import_factor))

        subt1, subt2 = st.columns(2)
        with subt1:
            st.dataframe(style_brl_table(taxes_df), use_container_width=True, hide_index=True)
        with subt2:
            st.dataframe(style_brl_table(memory_df), use_container_width=True, hide_index=True)

        inputs_dict = inputs.__dict__.copy()
        xlsx_bytes = make_excel_export(result, official, inputs_dict, taxes_df, memory_df, breakdown_df)
        pdf_bytes = build_pdf_report(official, inputs_dict, result, taxes_df, memory_df)
        d1, d2 = st.columns(2)
        d1.download_button(
            label="⬇️ Baixar memória de cálculo (Excel)",
            data=xlsx_bytes,
            file_name=f"assistente_importacao_v2_{official.ncm}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            key="btn_download_excel"
        )
        d2.download_button(
            label="⬇️ Baixar resumo executivo (PDF)",
            data=pdf_bytes,
            file_name=f"assistente_importacao_v2_{official.ncm}.pdf",
            mime="application/pdf",
            type="secondary",
            key="btn_download_pdf"
        )

with dashboard_tab:
    pack = st.session_state.result_pack
    if pack is None:
        st.info("Preencha a operação e clique em calcular para liberar o dashboard executivo.")
    else:
        result = pack["result"]
        breakdown_df = pack["breakdown_df"]
        st.subheader("Dashboard executivo")

        c1, c2, c3 = st.columns(3)
        c1.metric("Share tributos", pct(result.tax_share_pct))
        c2.metric("Share logística", pct(result.logistics_share_pct))
        c3.metric("Custo unitário BRL", brl(result.unit_landed_cost_brl))

        g1, g2 = st.columns(2)
        with g1:
            st.altair_chart(render_breakdown_chart(breakdown_df), use_container_width=True)
            st.caption("Fonte dos dados: cálculo consolidado do próprio app a partir das entradas da operação e das alíquotas consultadas.")
        with g2:
            st.altair_chart(render_waterfall_chart(result), use_container_width=True)
            st.caption("Fonte dos dados: memória de cálculo gerada pelo motor tributário/logístico da aplicação.")

        st.dataframe(style_brl_table(breakdown_df), use_container_width=True, hide_index=True)

with params_tab:
    st.subheader("Parâmetros editáveis")
    p1, p2 = st.columns(2)

    with p1:
        st.markdown("#### Tabela de ICMS por UF")
        edited_icms = st.data_editor(
            st.session_state.icms_df,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            key="icms_editor",
        )
        st.session_state.icms_df = edited_icms.copy()
        st.download_button(
            "Baixar tabela ICMS em CSV",
            data=st.session_state.icms_df.to_csv(index=False).encode("utf-8"),
            file_name="icms_uf_custom.csv",
            mime="text/csv",
            key="btn_download_icms_csv"
        )

    with p2:
        st.markdown("#### Tabela de premissas por porto")
        edited_ports = st.data_editor(
            st.session_state.port_df,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
            key="ports_editor",
        )
        st.session_state.port_df = edited_ports.copy()
        st.download_button(
            "Baixar tabela de portos em CSV",
            data=st.session_state.port_df.to_csv(index=False).encode("utf-8"),
            file_name="portos_custom.csv",
            mime="text/csv",
            key="btn_download_ports_csv"
        )

    st.info("Em ambiente cloud simples, essas edições ficam em sessão. Para persistência real, a próxima evolução ideal é salvar em banco ou SharePoint/OneLake.")

with docs_tab:
    st.subheader("Documentação operacional")
    st.markdown("""
    **Objetivo do app**
    - consolidar custo de importação marítima / longo curso;
    - buscar II e IPI em bases oficiais públicas;
    - estimar landed cost unitário e total;
    - exportar memória de cálculo em Excel e PDF.

    **Entradas críticas**
    - NCM;
    - quantidade, unidade, valor unitário e câmbio da mercadoria;
    - frete marítimo, moeda do frete e câmbio do frete;
    - país de origem, porto de origem, porto de destino e UF;
    - INCOTERM;
    - custos no Brasil e seguros.

    **Observações do MVP profissional**
    - II e IPI são consultados automaticamente nas bases públicas.
    - AFRMM é tratado para longo curso marítimo quando habilitado.
    - PIS, COFINS e ICMS continuam parametrizados porque o tratamento real pode depender de enquadramento legal, UF e detalhes da operação.
    - O país de origem já está no fluxo e abre caminho para a próxima camada de preferências tarifárias/acordos.
    """)
