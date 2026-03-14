import pdfplumber
import re
import pandas as pd
import streamlit as st
import io
import os
from fpdf import FPDF

# --- NUEVA CLASE PARA GENERAR EL PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Informe de Comparativa Energética', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generar_pdf(df, mejor_opcion):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    
    # Resumen de Ahorro
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Resumen de Estimación Anual", 0, 1)
    pdf.set_font("Arial", size=11)
    
    ahorro_anual = mejor_opcion['Ahorro'] * 12
    pdf.multi_cell(0, 10, f"Basado en el análisis, la mejor opción es {mejor_opcion['Compañía/Tarifa']}.\n"
                         f"Ahorro mensual estimado: {mejor_opcion['Ahorro']:.2f} €\n"
                         f"ESTIMACIÓN DE AHORRO ANUAL: {ahorro_anual:.2f} €")
    pdf.ln(10)
    
    # Tabla
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(70, 10, "Compañía/Tarifa", 1)
    pdf.cell(40, 10, "Coste Mes", 1)
    pdf.cell(40, 10, "Ahorro Mes", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=10)
    for i, row in df.head(15).iterrows(): # Top 15 para el PDF
        pdf.cell(70, 10, str(row['Compañía/Tarifa'])[:30], 1)
        pdf.cell(40, 10, f"{row['Coste (€)']} €", 1)
        pdf.cell(40, 10, f"{row['Ahorro']} €", 1)
        pdf.ln()
    
    return pdf.output()

def extraer_datos_factura(pdf_path):
    texto_completo = ""
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + "\n"

    # 1. Búsqueda de Consumos
    patrones_consumo = {
        'punta': [r'Consumo\s+en\s+P1:?\s*([\d,.]+)\s*kWh', r'Consumo\s+electricidad\s+Punta\s*([\d,.]+)\s*kWh'],
        'llano': [r'Consumo\s+en\s+P2:?\s*([\d,.]+)\s*kWh', r'Consumo\s+electricidad\s+Llano\s*([\d,.]+)\s*kWh'],
        'valle': [r'Consumo\s+en\s+P3:?\s*([\d,.]+)\s*kWh', r'Consumo\s+electricidad\s+Valle\s*([\d,.]+)\s*kWh']
    }
    
    consumos = {}
    for tramo, patrones in patrones_consumo.items():
        consumos[tramo] = 0.0
        for patron in patrones:
            match = re.search(patron, texto_completo, re.IGNORECASE)
            if match:
                consumos[tramo] = float(match.group(1).replace(',', '.'))
                break

    # 2. Búsqueda de Potencia
    patron_potencia = r'(?:Potencia\s+contratada(?:\s+en\s+punta-llano|\s+P1)?):\s*([\d,.]+)\s*kW'
    match_potencia = re.search(patron_potencia, texto_completo, re.IGNORECASE)
    potencia = float(match_potencia.group(1).replace(',', '.')) if match_potencia else 0.0

    # 3. Fecha y Días
    patron_fecha = r'(?:emitida\s+el|Fecha\s+de\s+emisión:)\s*([\d/]+\s*(?:de\s+\w+\s+de\s+)?\d{2,4})'
    match_fecha = re.search(patron_fecha, texto_completo, re.IGNORECASE)
    fecha = match_fecha.group(1) if match_fecha else "No encontrada"

    patron_dias = r'(\d+)\s*días'
    match_dias = re.search(patron_dias, texto_completo)
    dias = int(match_dias.group(1)) if match_dias else 0

    # 4. Excedentes
    patron_excedente = r'Valoración\s+excedentes\s*(?:-?\d+[\d,.]*\s*€/kWh)?\s*(-?\d+[\d,.]*)\s*kWh'
    match_excedente = re.search(patron_excedente, texto_completo, re.IGNORECASE)
    excedente = abs(float(match_excedente.group(1).replace(',', '.'))) if match_excedente else 0.0
    
    # --- Lógica específica de Factura Actual (Fila 0) ---
    total_real = 0.0
    es_xxi = re.search(r'Comercializadora\s+de\s+Referencia\s+Energética\s+por\s+XXI|Energía\s+XXI', texto_completo, re.IGNORECASE)
    
    if es_xxi:
        patron_pot_xxi = r'por\s+potencia\s+contratada\s*([\d,.]+)\s*€'
        patron_ene_xxi = r'por\s+energía\s+consumida\s*([\d,.]+)\s*€'
        m_pot = re.search(patron_pot_xxi, texto_completo, re.IGNORECASE)
        m_ene = re.search(patron_ene_xxi, texto_completo, re.IGNORECASE)
        val_pot = float(m_pot.group(1).replace(',', '.')) if m_pot else 0.0
        val_ene = float(m_ene.group(1).replace(',', '.')) if m_ene else 0.0
        total_real = val_pot + val_ene
    else:
        patron_total = r'(?:Subtotal|Importe\s+total|Total\s+factura)\s*:?\s*([\d,.]+)\s*€'
        match_total = re.search(patron_total, texto_completo, re.IGNORECASE)
        total_real = float(match_total.group(1).replace(',', '.')) if match_total else 0.0

    return {
        "Fecha": fecha, "Días": dias, "Potencia (kW)": potencia,
        "Consumo Punta (kWh)": consumos['punta'], "Consumo Llano (kWh)": consumos['llano'],
        "Consumo Valle (kWh)": consumos['valle'], "Excedente (kWh)": excedente,
        "Total Real": total_real
    }

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="Comparador Energético", layout="wide")
st.title("Comparador de Facturas Eléctricas")

excel_path = "tarifas_companias.xlsx"

if not os.path.exists(excel_path):
    st.error(f"No se encuentra el archivo '{excel_path}' en el repositorio de GitHub.")
else:
    uploaded_files = st.file_uploader("Sube tus facturas PDF (puedes subir varias de distintos meses)", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        datos_facturas = []
        for uploaded_file in uploaded_files:
            try:
                res = extraer_datos_factura(io.BytesIO(uploaded_file.read()))
                res['Archivo'] = uploaded_file.name
                datos_facturas.append(res)
            except Exception as e:
                st.error(f"Error procesando {uploaded_file.name}: {e}")

        if datos_facturas:
            df_resumen_pdfs = pd.DataFrame(datos_facturas)
            st.subheader("1. Datos Extraídos de los PDFs")
            st.write(df_resumen_pdfs[['Archivo', 'Fecha', 'Días', 'Potencia (kW)', 'Consumo Punta (kWh)', 'Consumo Llano (kWh)', 'Consumo Valle (kWh)', 'Excedente (kWh)']])

            df_tarifas = pd.read_excel(excel_path)
            resultados_finales = []

            # Cálculos para cada factura subida con cada tarifa del Excel
            for _, fact in df_resumen_pdfs.iterrows():
                # Primero añadimos la factura actual de ese mes
                resultados_finales.append({
                    "Mes/Fecha": fact['Fecha'],
                    "Compañía/Tarifa": "--- FACTURA ACTUAL ---",
                    "Factura": fact['Archivo'],
                    "Coste (€)": fact['Total Real'],
                    "Ahorro": 0.0
                })

                # Luego calculamos todas las opciones del Excel para ese mes concreto
                for index, tarifa in df_tarifas.iterrows():
                    try:
                        nombre_cia = tarifa.iloc[0]
                        b_pot1 = pd.to_numeric(tarifa.iloc[1], errors='coerce')
                        c_pot2 = pd.to_numeric(tarifa.iloc[2], errors='coerce')
                        d_punta = pd.to_numeric(tarifa.iloc[3], errors='coerce')
                        e_llano = pd.to_numeric(tarifa.iloc[4], errors='coerce')
                        f_valle = pd.to_numeric(tarifa.iloc[5], errors='coerce')
                        g_excedente = pd.to_numeric(tarifa.iloc[6], errors='coerce')

                        coste = (fact['Días'] * b_pot1 * fact['Potencia (kW)']) + \
                                (fact['Días'] * c_pot2 * fact['Potencia (kW)']) + \
                                (fact['Consumo Punta (kWh)'] * d_punta) + \
                                (fact['Consumo Llano (kWh)'] * e_llano) + \
                                (fact['Consumo Valle (kWh)'] * f_valle) - \
                                (fact['Excedente (kWh)'] * g_excedente)
                        
                        resultados_finales.append({
                            "Mes/Fecha": fact['Fecha'],
                            "Compañía/Tarifa": nombre_cia,
                            "Factura": fact['Archivo'],
                            "Coste (€)": round(coste, 2),
                            "Ahorro": round(fact['Total Real'] - coste, 2)
                        })
                    except: continue

            # Tabla final
            df_comparativa = pd.DataFrame(resultados_finales).dropna(subset=['Coste (€)'])
            
            # ORDENACIÓN CLAVE: Primero por Fecha, luego por Coste de menor a mayor
            df_comparativa = df_comparativa.sort_values(by=["Mes/Fecha", "Coste (€)"], ascending=[True, True]).reset_index(drop=True)

            st.subheader("2. Comparativa Final (Ordenada por Mes y Ahorro)")
            st.dataframe(df_comparativa, use_container_width=True)

            # --- NUEVA SECCIÓN DE EXPORTACIÓN ---
            st.divider()
            # Buscamos la mejor opción (excluyendo la factura actual)
            opciones_ahorro = df_comparativa[df_comparativa["Compañía/Tarifa"] != "--- FACTURA ACTUAL ---"]
            if not opciones_ahorro.empty:
                mejor = opciones_ahorro.iloc[0]
                pdf_data = generar_pdf(df_comparativa, mejor)
                
                st.download_button(
                    label="📥 Descargar Comparativa en PDF",
                    data=pdf_data,
                    file_name="Comparativa_Energia.pdf",
                    mime="application/pdf"
                )
