
import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import os

st.set_page_config(page_title="Comparador Luz Pro", layout="wide")

st.title("⚡ Comparador de Tarifas Eléctricas")
st.markdown("Esta app analiza tus facturas y busca la mejor compañía según tu consumo real.")

# --- CONFIGURACIÓN DE LA BASE DE DATOS POR DEFECTO ---
ARCHIVO_DB_POR_DEFECTO = "tarifas_companias.xlsx"

if os.path.exists(ARCHIVO_DB_POR_DEFECTO):
    try:
        df_raw = pd.read_excel(ARCHIVO_DB_POR_DEFECTO, header=1)
        st.sidebar.success(f"✅ Base de datos '{ARCHIVO_DB_POR_DEFECTO}' cargada.")
    except Exception as e:
        st.sidebar.error(f"Error al leer el Excel: {e}")
        df_raw = None
else:
    st.sidebar.warning("⚠️ No se encontró la base de datos por defecto.")
    archivo_subido = st.sidebar.file_uploader("Sube tu Excel de Tarifas manualmente", type=["xlsx"])
    if archivo_subido:
        df_raw = pd.read_excel(archivo_subido, header=1)
    else:
        df_raw = None

# --- FUNCIÓN DE EXTRACCIÓN MEJORADA (MERCADO LIBRE + ENERGÍA XXI) ---
def extraer_datos(archivo_pdf):
    texto_completo = ""
    with pdfplumber.open(archivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto_content = pagina.extract_text()
            if texto_content:
                texto_completo += texto_content + "\n"

    # Extracción de Fecha
    match_fecha = re.search(r"(\d{2}/\d{2}/\d{4})", texto_completo)
    fecha_factura = match_fecha.group(1) if match_fecha else "S/D"

    # Extracción de Días (Mejorado para Energía XXI)
    match_dias = re.search(r"Periodo\s+de\s+consumo:.*?\((\d+)\s*días\)", texto_completo, re.IGNORECASE)
    if not match_dias:
        match_dias = re.search(r"Potencia\s+P1.*?kW.*?(\d+)\s*días", texto_completo, re.IGNORECASE)
    dias_factura = int(match_dias.group(1)) if match_dias else 30

    # Extracción de Potencia (Mejorado para Energía XXI)
    match_potencia = re.search(r"Potencia\s+contratada.*?(\d+[.,]\d+|\d+)\s*kW", texto_completo, re.IGNORECASE)
    if not match_potencia:
        match_potencia = re.search(r"Potencia\s+P1\s*(\d+[.,]\d+|\d+)\s*kW", texto_completo, re.IGNORECASE)
    potencia_factura = float(match_potencia.group(1).replace(',', '.')) if match_potencia else 3.3

    # Extracción de Consumos (Compatible con Energía XXI y Mercado Libre)
    patrones_kwh = {
        "Punta": r"(?:consumo\s+electricidad\s+punta|Consumo\s+en\s+P1).*?(\d+[.,]?\d*)\s*kWh",
        "Llano": r"(?:consumo\s+electricidad\s+llano|Consumo\s+en\s+P2).*?(\d+[.,]?\d*)\s*kWh",
        "Valle": r"(?:consumo\s+electricidad\s+valle|Consumo\s+en\s+P3).*?(\d+[.,]?\d*)\s*kWh",
        "Excedentes": r"(?:Excedentes|Energía\s+vertida|Valoración\s+excedentes).*?(-?\d+[.,]?\d*)\s*kWh"
    }
    
    consumos = {}
    for k, p in patrones_kwh.items():
        match = re.search(p, texto_completo, re.IGNORECASE | re.DOTALL)
        if match:
            consumos[k] = float(match.group(1).replace(',', '.'))
        else:
            consumos[k] = 0.0
    
    # Importe Real
    match_actual = re.search(r"(?:IMPORTE\s+FACTURA:|Total\s+importe|Total\s+factura).*?(\d+[.,]\d+)\s*€", texto_completo, re.IGNORECASE)
    importe_real = float(match_actual.group(1).replace(',', '.')) if match_actual else 0.0
        
    return {
        "archivo": archivo_pdf.name, 
        "fecha": fecha_factura, 
        "dias": dias_factura, 
        "potencia": potencia_factura, 
        "consumos": consumos, 
        "importe_real": importe_real
    }

# --- INTERFAZ Y PROCESAMIENTO ---
st.header("Sube tus facturas PDF")
archivos_pdf = st.file_uploader("Selecciona uno o varios PDFs", type=["pdf"], accept_multiple_files=True)

if df_raw is not None and archivos_pdf:
    df_tarifas = df_raw.iloc[:, [0, 1, 2, 3, 4, 5, 6]].copy()
    df_tarifas.columns = ['Compania', 'Pot_P1', 'Pot_P2', 'Ene_Punta', 'Ene_Llano', 'Ene_Valle', 'Precio_Exc']
    df_tarifas = df_tarifas.dropna(subset=['Compania'])

    resultados = []

    for pdf in archivos_pdf:
        datos_pdf = extraer_datos(pdf)
        exc_kwh = abs(datos_pdf['consumos']['Excedentes'])
        
        resultados.append({
            "Archivo": datos_pdf['archivo'], 
            "Fecha": datos_pdf['fecha'], 
            "Compañía": "🏠 ACTUAL (PDF)",
            "Punta": datos_pdf['consumos']['Punta'], 
            "Llano": datos_pdf['consumos']['Llano'], 
            "Valle": datos_pdf['consumos']['Valle'],
            "Exc": exc_kwh, 
            "TOTAL (€)": datos_pdf['importe_real']
        })

        for _, fila in df_tarifas.iterrows():
            try:
                p_pot_total = float(fila['Pot_P1']) + float(fila['Pot_P2'])
                coste_fijo = datos_pdf['potencia'] * datos_pdf['dias'] * p_pot_total
                coste_variable = (datos_pdf['consumos']['Punta'] * float(fila['Ene_Punta']) + 
                                  datos_pdf['consumos']['Llano'] * float(fila['Ene_Llano']) + 
                                  datos_pdf['consumos']['Valle'] * float(fila['Ene_Valle']))
                total_simulado = coste_fijo + coste_variable - (exc_kwh * float(fila['Precio_Exc']))
                
                resultados.append({
                    "Archivo": datos_pdf['archivo'], 
                    "Fecha": datos_pdf['fecha'], 
                    "Compañía": str(fila['Compania']),
                    "Punta": datos_pdf['consumos']['Punta'], 
                    "Llano": datos_pdf['consumos']['Llano'], 
                    "Valle": datos_pdf['consumos']['Valle'],
                    "Exc": exc_kwh, 
                    "TOTAL (€)": round(total_simulado, 2)
                })
            except:
                continue

    df_final = pd.DataFrame(resultados).sort_values(by=["Archivo", "TOTAL (€)"])
    st.write("### 📊 Resultados de la comparativa")
    st.dataframe(df_final, use_container_width=True)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False)
    st.download_button("📥 Descargar reporte en Excel", data=buffer.getvalue(), file_name="comparativa_luz.xlsx")

elif df_raw is None:
    st.error("Sube el archivo 'tarifas_companias.xlsx' en el panel lateral.")
else:
    st.info("Sube tus facturas PDF para comenzar.")
