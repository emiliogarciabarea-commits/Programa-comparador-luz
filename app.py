
import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import os

st.set_page_config(page_title="Comparador Luz Pro", layout="wide")

st.title("⚡ Comparador de Tarifas (Costo Neto)")
st.markdown("Analizador compatible con facturas de **Energía XXI (P1, P2, P3)** y **Naturgy**.")

# --- CARGA DE BASE DE DATOS ---
ARCHIVO_DB_POR_DEFECTO = "tarifas_companias.xlsx"
df_raw = None

if os.path.exists(ARCHIVO_DB_POR_DEFECTO):
    try:
        df_raw = pd.read_excel(ARCHIVO_DB_POR_DEFECTO, header=1)
        st.sidebar.success("✅ Tarifas cargadas.")
    except: pass
else:
    subida = st.sidebar.file_uploader("Sube el Excel de Tarifas", type=["xlsx"])
    if subida: df_raw = pd.read_excel(subida, header=1)

# --- FUNCIÓN DE EXTRACCIÓN (Lógica de búsqueda dual) ---
def extraer_datos(archivo_pdf):
    texto_completo = ""
    with pdfplumber.open(archivo_pdf) as pdf:
        for pagina in pdf.pages:
            content = pagina.extract_text()
            if content: texto_completo += content + "\n"

    # A. Fecha y Días
    m_fecha = re.search(r"(\d{2}/\d{2}/\d{4})", texto_completo)
    fecha = m_fecha.group(1) if m_fecha else "S/D"
    
    m_dias = re.search(r"(\d+)\s*días", texto_completo, re.IGNORECASE)
    dias = int(m_dias.group(1)) if m_dias else 30

    # B. Potencia (Número seguido de kW, ignorando kWh)
    m_pot = re.search(r"(\d+[.,]\d+|\d+)\s*kW(?!h)", texto_completo, re.IGNORECASE)
    potencia = float(m_pot.group(1).replace(',', '.')) if m_pot else 3.3

    # C. Consumos (Mapeo de etiquetas Naturgy vs Energía XXI)
    def buscar_consumo(lista_patrones, texto):
        for p in lista_patrones:
            # Busca el patrón y extrae el primer número seguido de kWh
            match = re.search(p + r".*?(\d+[.,]\d+|\d+)\s*kWh", texto, re.IGNORECASE | re.DOTALL)
            if match:
                return float(match.group(1).replace(',', '.'))
        return 0.0

    consumos = {
        "Punta": buscar_consumo([r"Consumo electricidad Punta", r"P1"], texto_completo),
        "Llano": buscar_consumo([r"Consumo electricidad Llano", r"P2"], texto_completo),
        "Valle": buscar_consumo([r"Consumo electricidad Valle", r"P3"], texto_completo),
        "Excedentes": buscar_consumo([r"Excedentes", r"Energía vertida", r"P4"], texto_completo)
    }

    # D. Importe Neto (Potencia + Energía antes de impuestos)
    m_p = re.search(r"(?:potencia contratada|Facturación por potencia).*?(\d+[.,]\d+)", texto_completo, re.IGNORECASE)
    m_e = re.search(r"(?:energía consumida|Facturación por energía).*?(\d+[.,]\d+)", texto_completo, re.IGNORECASE)
    
    val_p = float(m_p.group(1).replace(',', '.')) if m_p else 0.0
    val_e = float(m_e.group(1).replace(',', '.')) if m_e else 0.0
    neto_real = round(val_p + val_e, 2)
        
    return {
        "archivo": archivo_pdf.name, "fecha": fecha, "dias": dias, 
        "potencia": potencia, "consumos": consumos, "neto_real": neto_real
    }

# --- PROCESAMIENTO ---
pdfs = st.file_uploader("Sube tus facturas PDF", type=["pdf"], accept_multiple_files=True)

if df_raw is not None and pdfs:
    df_tarifas = df_raw.iloc[:, [0, 1, 2, 3, 4, 5, 6]].copy()
    df_tarifas.columns = ['Compania', 'Pot_P1', 'Pot_P2', 'Ene_Punta', 'Ene_Llano', 'Ene_Valle', 'Precio_Exc']
    df_tarifas = df_tarifas.dropna(subset=['Compania'])

    res = []
    for pdf in pdfs:
        try:
            d = extraer_datos(pdf)
            # Fila Actual
            res.append({
                "Archivo": d['archivo'], "Compañía": "🏠 ACTUAL (NETO PDF)",
                "Punta (kWh)": d['consumos']['Punta'], "Llano (kWh)": d['consumos']['Llano'], 
                "Valle (kWh)": d['consumos']['Valle'], "COSTO NETO (€)": d['neto_real']
            })
            # Simulaciones
            for _, fila in df_tarifas.iterrows():
                fijo = d['potencia'] * d['dias'] * (float(fila['Pot_P1']) + float(fila['Pot_P2']))
                var = (d['consumos']['Punta'] * float(fila['Ene_Punta']) + 
                       d['consumos']['Llano'] * float(fila['Ene_Llano']) + 
                       d['consumos']['Valle'] * float(fila['Ene_Valle']))
                exc = abs(d['consumos']['Excedentes']) * float(fila['Precio_Exc'])
                total_sim = round(fijo + var - exc, 2)
                res.append({
                    "Archivo": d['archivo'], "Compañía": str(fila['Compania']),
                    "Punta (kWh)": d['consumos']['Punta'], "Llano (kWh)": d['consumos']['Llano'], 
                    "Valle (kWh)": d['consumos']['Valle'], "COSTO NETO (€)": total_sim
                })
        except Exception as e:
            st.error(f"Error procesando {pdf.name}: {e}")

    if res:
        st.dataframe(pd.DataFrame(res).sort_values(by=["Archivo", "COSTO NETO (€)"]), use_container_width=True)
