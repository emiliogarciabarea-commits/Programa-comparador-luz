
import pdfplumber
import re
import pandas as pd
import streamlit as st
import io
import os

def extraer_datos_factura(pdf_path):
    texto_completo = ""
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + "\n"

    # --- DETECCIÓN DE TIPO DE FACTURA ---
    es_el_corte_ingles = re.search(r'Energía\s+El\s+Corte\s+Inglés|TELECOR', texto_completo, re.IGNORECASE)
    es_iberdrola = re.search(r'IBERDROLA\s+CLIENTES', texto_completo, re.IGNORECASE)
    es_naturgy = re.search(r'Naturgy', texto_completo, re.IGNORECASE)
    es_repsol = re.search(r'repsol', texto_completo, re.IGNORECASE)
    es_endesa_luz = re.search(r'Endesa\s+Energía', texto_completo, re.IGNORECASE)
    es_total_energies = re.search(r'TotalEnergies', texto_completo, re.IGNORECASE)
    es_xxi = re.search(r'Energía\s+XXI', texto_completo, re.IGNORECASE)

    # Inicialización de variables por defecto
    consumos = {'punta': 0.0, 'llano': 0.0, 'valle': 0.0}
    potencia = 0.0
    fecha = "No encontrada"
    dias = 0
    total_real = 0.0
    excedente = 0.0

    if es_el_corte_ingles:
        patron_cons_eci = r'Punta\s+Llano\s+Valle\s+Consumo\s+kWh\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)'
        match_cons = re.search(patron_cons_eci, texto_completo)
        if match_cons:
            consumos['punta'] = float(match_cons.group(1).replace(',', '.'))
            consumos['llano'] = float(match_cons.group(2).replace(',', '.'))
            consumos['valle'] = float(match_cons.group(3).replace(',', '.'))

        match_potencia = re.search(r'Potencia\s+contratada\s+kW\s+([\d,.]+)', texto_completo)
        potencia = float(match_potencia.group(1).replace(',', '.')) if match_potencia else 0.0
        
        match_fecha = re.search(r'Fecha\s+de\s+Factura:\s*([\d/]+)', texto_completo)
        fecha = match_fecha.group(1) if match_fecha else "No encontrada"
        
        match_dias = re.search(r'Días\s+de\s+consumo:\s*(\d+)', texto_completo)
        dias = int(match_dias.group(1)) if match_dias else 0
        
        match_total = re.search(r'TOTAL\s+FACTURA\s+([\d,.]+)\s*€', texto_completo)
        total_real = float(match_total.group(1).replace(',', '.')) if match_total else 0.0

    elif es_naturgy:
        # LÓGICA ESPECÍFICA PARA DÍAS (Solicitada: Alquiler de contador)
        # Busca "Alquiler de contador", salta texto intermedio y captura el número antes de "días"
        match_dias = re.search(r'Alquiler\s+de\s+contador\s+(\d+)\s+días', texto_completo, re.IGNORECASE)
        dias = int(match_dias.group(1)) if match_dias else 0

        # Resto de datos Naturgy
        match_fecha = re.search(r'Fecha\s+de\s+factura:\s*([\d/]{10})', texto_completo, re.IGNORECASE)
        fecha = match_fecha.group(1) if match_fecha else "No encontrada"

        match_pot = re.search(r'Potencia\s+contratada.*?([\d,.]+)\s*kW', texto_completo, re.IGNORECASE)
        potencia = float(match_pot.group(1).replace(',', '.')) if match_pot else 0.0

        # Consumos Naturgy (Patrón habitual P1, P2, P3)
        m_p1 = re.search(r'Punta\s+.*?([\d,.]+)\s*kWh', texto_completo, re.IGNORECASE)
        m_p2 = re.search(r'Llano\s+.*?([\d,.]+)\s*kWh', texto_completo, re.IGNORECASE)
        m_p3 = re.search(r'Valle\s+.*?([\d,.]+)\s*kWh', texto_completo, re.IGNORECASE)
        consumos['punta'] = float(m_p1.group(1).replace(',', '.')) if m_p1 else 0.0
        consumos['llano'] = float(m_p2.group(1).replace(',', '.')) if m_p2 else 0.0
        consumos['valle'] = float(m_p3.group(1).replace(',', '.')) if m_p3 else 0.0

        match_total = re.search(r'Importe\s+total\s+factura.*?([\d,.]+)\s*€', texto_completo, re.IGNORECASE)
        total_real = float(match_total.group(1).replace(',', '.')) if match_total else 0.0

    elif es_total_energies:
        m_fecha = re.search(r'Fecha\s+emisión:\s*([\d.]{10})', texto_completo, re.IGNORECASE)
        fecha = m_fecha.group(1) if m_fecha else "No encontrada"
        m_dias_meta = re.search(r'(\d+)\s+día\(s\)', texto_completo, re.IGNORECASE)
        dias = int(m_dias_meta.group(1)) if m_dias_meta else 0
        m_pot_meta = re.search(r'Potencia\s+P1:\s*([\d,.]+)', texto_completo, re.IGNORECASE)
        potencia = float(m_pot_meta.group(1).replace(',', '.')) if m_pot_meta else 0.0

        total_real = 0.0
        lineas = texto_completo.split('\n')
        for linea in lineas:
            linea_limpia = linea.strip()
            if re.search(r'^(\d{2}\.\d{2}\.\d{4})|(\d+\s+día\(s\))', linea_limpia):
                m_valor = re.findall(r'([\d,.]+)\s*€\s*$', linea_limpia)
                if m_valor:
                    total_real += float(m_valor[-1].replace('.', '').replace(',', '.'))

        def extraer_kwh(tipo, texto):
            patron = rf'{tipo}.*?([\d,.]+)\s*kWh'
            matches = re.findall(patron, texto, re.IGNORECASE)
            if matches: return float(matches[-1].replace('.', '').replace(',', '.'))
            return 0.0

        consumos = {
            'punta': extraer_kwh('Punta', texto_completo),
            'llano': extraer_kwh('Llano', texto_completo),
            'valle': extraer_kwh('Valle', texto_completo)
        }
        if sum(consumos.values()) == 0:
            m_gen = re.search(r'(\d+)\s*kWh\s+[\d,.]+\s*€/kWh', texto_completo)
            if m_gen: consumos['punta'] = float(m_gen.group(1))

    elif es_endesa_luz:
        m_fecha_etiqueta = re.search(r'Fecha\s+emisión\s+factura:\s*([\d/]{10})', texto_completo, re.IGNORECASE)
        fecha = m_fecha_etiqueta.group(1) if m_fecha_etiqueta else "No encontrada"
        m_dias = re.search(r'(\d+)\s+días', texto_completo, re.IGNORECASE)
        dias = int(m_dias.group(1)) if m_dias else 0
        m_pot = re.search(r'punta-llano\s*([\d,.]+)\s*kW', texto_completo, re.IGNORECASE)
        potencia = float(m_pot.group(1).replace(',', '.')) if m_pot else 0.0

        m_punta = re.search(r'Punta\s+[\d,.]+\s+[\d,.]+\s+[\d,.]+\s+[\w,.]+\s+([\d,.]+)', texto_completo, re.IGNORECASE)
        m_llano = re.search(r'Llano\s+[\d,.]+\s+[\d,.]+\s+[\d,.]+\s+[\w,.]+\s+([\d,.]+)', texto_completo, re.IGNORECASE)
        m_valle = re.search(r'Valle\s+[\d,.]+\s+[\d,.]+\s+[\d,.]+\s+[\w,.]+\s+([\d,.]+)', texto_completo, re.IGNORECASE)
        consumos = {
            'punta': float(m_punta.group(1).replace(',', '.')) if m_punta else 0.0,
            'llano': float(m_llano.group(1).replace(',', '.')) if m_llano else 0.0,
            'valle': float(m_valle.group(1).replace(',', '.')) if m_valle else 0.0
        }

    elif es_repsol:
        m_fecha = re.search(r'Fecha\s+de\s+emisión\s*([\d/]+)', texto_completo, re.IGNORECASE)
        fecha = m_fecha.group(1) if m_fecha else "No encontrada"
        m_pot = re.search(r'Potencia\s+contratada\s*([\d,.]+)\s*kW', texto_completo, re.IGNORECASE)
        potencia = float(m_pot.group(1).replace(',', '.')) if m_pot else 0.0
        m_dias = re.search(r'Días\s+facturados\s*(\d+)', texto_completo, re.IGNORECASE)
        dias = int(m_dias.group(1)) if m_dias else 0
        m_consumo_gen = re.search(r'Consumo\s+en\s+este\s+periodo\s*([\d,.]+)\s*kWh', texto_completo, re.IGNORECASE)
        consumos['punta'] = float(m_consumo_gen.group(1).replace(',', '.')) if m_consumo_gen else 0.0

    elif es_iberdrola:
        match_potencia = re.search(r'Potencia\s+punta:\s*([\d,.]+)\s*kW', texto_completo, re.IGNORECASE)
        potencia = float(match_potencia.group(1).replace(',', '.')) if match_potencia else 0.0
        match_dias = re.search(r'Potencia\s+facturada.*?(\d+)\s+días', texto_completo, re.IGNORECASE | re.DOTALL)
        dias = int(match_dias.group(1)) if match_dias else 0
        match_periodo = re.search(r'PERIODO\s+DE\s+FACTURACIÓN:?.*?(\d{2}/\d{2}/\d{2,4}).*?(\d{2}/\d{2}/\d{2,4})', texto_completo, re.IGNORECASE | re.DOTALL)
        fecha = match_periodo.group(2) if match_periodo else "No encontrada"
        m_punta = re.search(r'Punta\s*([\d,.]+)\s*kWh', texto_completo)
        m_llano = re.search(r'Llano\s*([\d,.]+)\s*kWh', texto_completo)
        m_valle = re.search(r'Valle\s*([\d,.]+)\s*kWh', texto_completo)
        consumos = {
            'punta': float(m_punta.group(1).replace(',', '.')) if m_punta else 0.0,
            'llano': float(m_llano.group(1).replace(',', '.')) if m_llano else 0.0,
            'valle': float(m_valle.group(1).replace(',', '.')) if m_valle else 0.0
        }

    else:
        # Lógica genérica y Energía XXI
        patrones_consumo = {
            'punta': [r'Consumo\s+en\s+P1:?\s*([\d,.]+)\s*kWh', r'Consumo\s+electricidad\s+Punta\s*([\d,.]+)\s*kWh'],
            'llano': [r'Consumo\s+en\s+P2:?\s*([\d,.]+)\s*kWh', r'Consumo\s+electricidad\s+Llano\s*([\d,.]+)\s*kWh'],
            'valle': [r'Consumo\s+en\s+P3:?\s*([\d,.]+)\s*kWh', r'Consumo\s+electricidad\s+Valle\s*([\d,.]+)\s*kWh']
        }
        for tramo, patrones in patrones_consumo.items():
            for patron in patrones:
                match = re.search(patron, texto_completo, re.IGNORECASE)
                if match:
                    consumos[tramo] = float(match.group(1).replace(',', '.'))
                    break
        match_potencia = re.search(r'(?:Potencia\s+contratada(?:\s+en\s+punta-llano|\s+P1)?):\s*([\d,.]+)\s*kW', texto_completo, re.IGNORECASE)
        potencia = float(match_potencia.group(1).replace(',', '.')) if match_potencia else 0.0
        match_fecha = re.search(r'(?:emitida\s+el|Fecha\s+de\s+emisión:)\s*([\d/]+\s*(?:de\s+\w+\s+de\s+)?\d{2,4})', texto_completo, re.IGNORECASE)
        fecha = match_fecha.group(1) if match_fecha else "No encontrada"
        match_dias = re.search(r'(\d+)\s*días', texto_completo)
        dias = int(match_dias.group(1)) if match_dias else 0
        match_excedente = re.search(r'Valoración\s+excedentes\s*(?:-?\d+[\d,.]*\s*€/kWh)?\s*(-?\d+[\d,.]*)\s*kWh', texto_completo, re.IGNORECASE)
        excedente = abs(float(match_excedente.group(1).replace(',', '.'))) if match_excedente else 0.0
        
        match_total = re.search(r'(?:Subtotal|Importe\s+total|Total\s+factura)\s*:?\s*([\d,.]+)\s*€', texto_completo, re.IGNORECASE)
        total_real = float(match_total.group(1).replace(',', '.')) if match_total else 0.0

    return {
        "Fecha": fecha, "Días": dias, "Potencia (kW)": potencia,
        "Consumo Punta (kWh)": consumos['punta'], "Consumo Llano (kWh)": consumos['llano'],
        "Consumo Valle (kWh)": consumos['valle'], "Excedente (kWh)": excedente,
        "Total Real": round(total_real, 2)
    }

# --- STREAMLIT UI ---
st.set_page_config(page_title="Comparador Energético", layout="wide")
st.title("⚡ Comparador de Facturas Eléctricas Pro")

excel_path = "tarifas_companias.xlsx"

if not os.path.exists(excel_path):
    st.error(f"No se encuentra el archivo '{excel_path}' en el repositorio.")
else:
    uploaded_files = st.file_uploader("Sube tus facturas PDF", type="pdf", accept_multiple_files=True)

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
            with st.expander("🔍 Ver y corregir datos extraídos", expanded=True):
                df_resumen_pdfs = st.data_editor(df_resumen_pdfs, use_container_width=True, hide_index=True)

            df_tarifas = pd.read_excel(excel_path)
            resultados_finales = []

            for _, fact in df_resumen_pdfs.iterrows():
                resultados_finales.append({
                    "Mes/Fecha": fact['Fecha'],
                    "Compañía/Tarifa": "📍 TU FACTURA ACTUAL",
                    "Coste (€)": fact['Total Real'],
                    "Ahorro": 0.0,
                    "Dias_Factura": fact['Días']
                })

                for index, tarifa in df_tarifas.iterrows():
                    try:
                        nombre_cia = tarifa.iloc[0]
                        b_pot1 = pd.to_numeric(tarifa.iloc[1], errors='coerce')
                        c_pot2 = pd.to_numeric(tarifa.iloc[2], errors='coerce')
                        d_punta = pd.to_numeric(tarifa.iloc[3], errors='coerce')
                        e_llano = pd.to_numeric(tarifa.iloc[4], errors='coerce')
                        f_valle = pd.to_numeric(tarifa.iloc[5], errors='coerce')
                        g_excedente = pd.to_numeric(tarifa.iloc[6], errors='coerce')

                        coste_estimado = (fact['Días'] * b_pot1 * fact['Potencia (kW)']) + \
                                         (fact['Días'] * c_pot2 * fact['Potencia (kW)']) + \
                                         (fact['Consumo Punta (kWh)'] * d_punta) + \
                                         (fact['Consumo Llano (kWh)'] * e_llano) + \
                                         (fact['Consumo Valle (kWh)'] * f_valle) - \
                                         (fact['Excedente (kWh)'] * g_excedente)
                        
                        ahorro = fact['Total Real'] - coste_estimado
                        resultados_finales.append({
                            "Mes/Fecha": fact['Fecha'], "Compañía/Tarifa": nombre_cia,
                            "Coste (€)": round(coste_estimado, 2), "Ahorro": round(ahorro, 2),
                            "Dias_Factura": fact['Días']
                        })
                    except: continue

            df_comp = pd.DataFrame(resultados_finales).dropna(subset=['Coste (€)'])
            df_comp = df_comp.sort_values(by=["Mes/Fecha", "Ahorro"], ascending=[True, False])
            df_solo_ofertas = df_comp[df_comp["Compañía/Tarifa"] != "📍 TU FACTURA ACTUAL"]
            ranking_total = df_solo_ofertas.groupby("Compañía/Tarifa")["Ahorro"].sum().reset_index()
            ranking_total = ranking_total.sort_values(by="Ahorro", ascending=False)

            st.divider()
            
            if not ranking_total.empty:
                mejor_opcion_nombre = ranking_total.iloc[0]['Compañía/Tarifa']
                st.subheader("🏆 Resultado del Análisis")
                c1, c2 = st.columns(2)
                with c1: st.success(f"La mejor compañía es: **{mejor_opcion_nombre}**")
                with c2: st.metric(label="Ahorro Total Acumulado", value=f"{round(ranking_total.iloc[0]['Ahorro'], 2)} €")

            st.subheader("📊 Comparativa Detallada por Factura")
            st.dataframe(df_comp.drop(columns=['Dias_Factura'], errors='ignore'), use_container_width=True, hide_index=True)

            buffer_excel = io.BytesIO()
            with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                df_comp.to_excel(writer, index=False, sheet_name='Detalle Comparativa')
                ranking_total.to_excel(writer, index=False, sheet_name='Ranking Ahorro')

            st.download_button(
                label="📥 Descargar Informe Completo",
                data=buffer_excel.getvalue(),
                file_name="estudio_ahorro_energetico.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
