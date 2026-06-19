from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd


@dataclass
class ImportInputs:
    quantity: float
    unit: str
    unit_price_foreign: float
    product_currency: str
    product_fx_to_brl: float
    freight_foreign: float
    freight_currency: str
    freight_fx_to_brl: float
    country_of_origin: str
    port_origin: str
    port_destination: str
    uf_destination: str
    port_costs_brl: float
    customs_clearance_brl: float
    ncm: str
    incoterm: str
    intl_insurance_pct: float
    inland_freight_brl: float
    inland_insurance_pct: float
    pis_rate: float
    cofins_rate: float
    icms_rate: float
    include_afrmm: bool = True


@dataclass
class ImportResult:
    merchandise_foreign: float
    merchandise_brl: float
    freight_brl: float
    intl_insurance_brl: float
    customs_value_brl: float
    ii_rate: float
    ii_value_brl: float
    ipi_rate: float
    ipi_value_brl: float
    pis_rate: float
    pis_value_brl: float
    cofins_rate: float
    cofins_value_brl: float
    afrmm_rate: float
    afrmm_value_brl: float
    icms_rate: float
    icms_value_brl: float
    port_costs_brl: float
    customs_clearance_brl: float
    inland_freight_brl: float
    inland_insurance_brl: float
    total_landed_cost_brl: float
    unit_landed_cost_brl: float
    unit_landed_cost_foreign: float
    tax_share_pct: float
    logistics_share_pct: float
    import_factor: float
    memory: Dict[str, float]
    waterfall_rows: List[dict]


def _pct(value: float) -> float:
    return (value or 0.0) / 100.0


def components_in_incoterm(incoterm: str) -> dict:
    term = (incoterm or "").strip().upper()
    includes_international_freight = term in {"CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"}
    includes_international_insurance = term in {"CIF", "CIP"}
    return {
        "includes_international_freight": includes_international_freight,
        "includes_international_insurance": includes_international_insurance,
    }


def calculate_import_costs(inputs: ImportInputs, ii_rate: float, ipi_rate: float) -> ImportResult:
    merchandise_foreign = inputs.quantity * inputs.unit_price_foreign
    merchandise_brl = merchandise_foreign * inputs.product_fx_to_brl
    freight_brl = inputs.freight_foreign * inputs.freight_fx_to_brl

    incoterm_flags = components_in_incoterm(inputs.incoterm)

    intl_insurance_base = merchandise_brl + (0.0 if incoterm_flags["includes_international_freight"] else freight_brl)
    intl_insurance_brl = intl_insurance_base * _pct(inputs.intl_insurance_pct)

    customs_value_brl = merchandise_brl
    if not incoterm_flags["includes_international_freight"]:
        customs_value_brl += freight_brl
    if not incoterm_flags["includes_international_insurance"]:
        customs_value_brl += intl_insurance_brl

    ii_value = customs_value_brl * _pct(ii_rate)
    ipi_base = customs_value_brl + ii_value
    ipi_value = ipi_base * _pct(ipi_rate)

    pis_base = customs_value_brl + ii_value + ipi_value
    pis_value = pis_base * _pct(inputs.pis_rate)
    cofins_value = pis_base * _pct(inputs.cofins_rate)

    afrmm_rate = 25.0 if inputs.include_afrmm else 0.0
    afrmm_value = freight_brl * _pct(afrmm_rate)

    inland_insurance_brl = inputs.inland_freight_brl * _pct(inputs.inland_insurance_pct)

    icms_base_pre = (
        customs_value_brl + ii_value + ipi_value + pis_value + cofins_value + afrmm_value
        + inputs.port_costs_brl + inputs.customs_clearance_brl + inputs.inland_freight_brl + inland_insurance_brl
    )

    icms_rate_decimal = _pct(inputs.icms_rate)
    if icms_rate_decimal >= 1:
        raise ValueError("Alíquota de ICMS inválida.")
    icms_value = icms_base_pre * icms_rate_decimal / (1 - icms_rate_decimal) if icms_rate_decimal > 0 else 0.0

    total_landed = icms_base_pre + icms_value
    unit_landed_brl = total_landed / inputs.quantity if inputs.quantity else 0.0
    unit_landed_foreign = unit_landed_brl / inputs.product_fx_to_brl if inputs.product_fx_to_brl else 0.0

    total_taxes = ii_value + ipi_value + pis_value + cofins_value + afrmm_value + icms_value
    total_logistics = freight_brl + intl_insurance_brl + inputs.port_costs_brl + inputs.customs_clearance_brl + inputs.inland_freight_brl + inland_insurance_brl
    tax_share_pct = (total_taxes / total_landed * 100.0) if total_landed else 0.0
    logistics_share_pct = (total_logistics / total_landed * 100.0) if total_landed else 0.0
    import_factor = (total_landed / merchandise_brl) if merchandise_brl else 0.0

    memory = {
        "Mercadoria (BRL)": merchandise_brl,
        "Frete marítimo (BRL)": freight_brl,
        "Seguro internacional (BRL)": intl_insurance_brl,
        "Valor aduaneiro (BRL)": customs_value_brl,
        "II (BRL)": ii_value,
        "IPI (BRL)": ipi_value,
        "PIS (BRL)": pis_value,
        "COFINS (BRL)": cofins_value,
        "AFRMM (BRL)": afrmm_value,
        "Custos portuários (BRL)": inputs.port_costs_brl,
        "Desembaraço (BRL)": inputs.customs_clearance_brl,
        "Frete porto → planta (BRL)": inputs.inland_freight_brl,
        "Seguro frete nacional (BRL)": inland_insurance_brl,
        "ICMS (BRL)": icms_value,
        "Total landed cost (BRL)": total_landed,
    }

    waterfall_rows = [
        {"Etapa": "Mercadoria", "Valor": merchandise_brl, "Grupo": "Base"},
        {"Etapa": "Frete marítimo", "Valor": freight_brl if not incoterm_flags["includes_international_freight"] else 0.0, "Grupo": "Logística internacional"},
        {"Etapa": "Seguro internacional", "Valor": intl_insurance_brl if not incoterm_flags["includes_international_insurance"] else 0.0, "Grupo": "Logística internacional"},
        {"Etapa": "II", "Valor": ii_value, "Grupo": "Tributos"},
        {"Etapa": "IPI", "Valor": ipi_value, "Grupo": "Tributos"},
        {"Etapa": "PIS", "Valor": pis_value, "Grupo": "Tributos"},
        {"Etapa": "COFINS", "Valor": cofins_value, "Grupo": "Tributos"},
        {"Etapa": "AFRMM", "Valor": afrmm_value, "Grupo": "Tributos"},
        {"Etapa": "Custos portuários", "Valor": inputs.port_costs_brl, "Grupo": "Custos no Brasil"},
        {"Etapa": "Desembaraço", "Valor": inputs.customs_clearance_brl, "Grupo": "Custos no Brasil"},
        {"Etapa": "Frete porto → planta", "Valor": inputs.inland_freight_brl, "Grupo": "Custos no Brasil"},
        {"Etapa": "Seguro frete nacional", "Valor": inland_insurance_brl, "Grupo": "Custos no Brasil"},
        {"Etapa": "ICMS", "Valor": icms_value, "Grupo": "Tributos"},
    ]

    return ImportResult(
        merchandise_foreign=merchandise_foreign,
        merchandise_brl=merchandise_brl,
        freight_brl=freight_brl,
        intl_insurance_brl=intl_insurance_brl,
        customs_value_brl=customs_value_brl,
        ii_rate=ii_rate,
        ii_value_brl=ii_value,
        ipi_rate=ipi_rate,
        ipi_value_brl=ipi_value,
        pis_rate=inputs.pis_rate,
        pis_value_brl=pis_value,
        cofins_rate=inputs.cofins_rate,
        cofins_value_brl=cofins_value,
        afrmm_rate=afrmm_rate,
        afrmm_value_brl=afrmm_value,
        icms_rate=inputs.icms_rate,
        icms_value_brl=icms_value,
        port_costs_brl=inputs.port_costs_brl,
        customs_clearance_brl=inputs.customs_clearance_brl,
        inland_freight_brl=inputs.inland_freight_brl,
        inland_insurance_brl=inland_insurance_brl,
        total_landed_cost_brl=total_landed,
        unit_landed_cost_brl=unit_landed_brl,
        unit_landed_cost_foreign=unit_landed_foreign,
        tax_share_pct=tax_share_pct,
        logistics_share_pct=logistics_share_pct,
        import_factor=import_factor,
        memory=memory,
        waterfall_rows=waterfall_rows,
    )


def memory_dataframe(result: ImportResult) -> pd.DataFrame:
    return pd.DataFrame(list(result.memory.items()), columns=["Etapa", "Valor (BRL)"])


def tax_dataframe(result: ImportResult) -> pd.DataFrame:
    rows = [
        ["II", result.ii_rate, result.ii_value_brl],
        ["IPI", result.ipi_rate, result.ipi_value_brl],
        ["PIS", result.pis_rate, result.pis_value_brl],
        ["COFINS", result.cofins_rate, result.cofins_value_brl],
        ["AFRMM", result.afrmm_rate, result.afrmm_value_brl],
        ["ICMS", result.icms_rate, result.icms_value_brl],
    ]
    return pd.DataFrame(rows, columns=["Tributo", "Alíquota (%)", "Valor (BRL)"])


def executive_breakdown_dataframe(result: ImportResult) -> pd.DataFrame:
    rows = [
        ["Mercadoria", result.merchandise_brl, "Base"],
        ["Logística internacional", result.freight_brl + result.intl_insurance_brl, "Logística"],
        ["Tributos federais + AFRMM", result.ii_value_brl + result.ipi_value_brl + result.pis_value_brl + result.cofins_value_brl + result.afrmm_value_brl, "Tributos"],
        ["Custos no Brasil", result.port_costs_brl + result.customs_clearance_brl + result.inland_freight_brl + result.inland_insurance_brl, "Custos no Brasil"],
        ["ICMS", result.icms_value_brl, "Tributos"],
    ]
    return pd.DataFrame(rows, columns=["Categoria", "Valor (BRL)", "Grupo"])
