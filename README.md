# Assistente de Importação Pro — V2

Versão 2 do projeto em Streamlit com foco em uso profissional.

## Upgrades implementados

1. **País de origem** incluído no fluxo.
2. **Tabela de ICMS por UF editável** dentro do app.
3. **Premissas de custos por porto editáveis** dentro do app.
4. **Exportação em PDF** além do Excel.
5. **Dashboard executivo** com composição de custo e waterfall.

## Estrutura

- `app.py` → interface Streamlit e dashboard
- `official_data.py` → consumo das bases oficiais de II/IPI/NCM
- `tax_engine.py` → motor de cálculo e dataframes executivos
- `config_data.py` → leitura das tabelas de parâmetros
- `pdf_export.py` → geração do PDF
- `data_icms_uf.csv` → tabela editável de ICMS por UF
- `data_port_defaults.csv` → premissas editáveis por porto

## Execução local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy sugerido

- Streamlit Community Cloud
- Azure Web App
- Render
- Railway

## Próxima camada recomendada

- preferências tarifárias por país de origem;
- ex-tarifário e regimes especiais;
- persistência das tabelas em banco/SharePoint;
- histórico de consultas;
- PDF corporativo com branding.
