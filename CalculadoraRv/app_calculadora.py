import streamlit as st
import pandas as pd
import sys
from datetime import date
from fpdf import FPDF # Importación de V20.0

# --- 0. FUNCIÓN AYUDANTE PARA CALCULAR EDAD ---
def calculate_age(born):
    """
    Calcula la edad exacta (años cumplidos) desde la fecha de nacimiento.
    """
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age

# --- 1. LOS MOTORES (CEREBRO) ---

@st.cache_data
def cargar_tablas_de_mortalidad_reales(arch_h_vejez, arch_m_vejez, arch_h_inv, arch_m_inv):
    """
    Carga las 4 Tablas de Mortalidad 2020 (Vejez e Invalidez)
    desde los archivos Excel oficiales. (Pilar 2)
    """
    try:
        # 1. Cargar Vejez
        df_h_vejez = pd.read_excel(
            arch_h_vejez, sheet_name='CB-2020, Hombres', skiprows=6, index_col='Edad'
        )
        df_m_vejez = pd.read_excel(
            arch_m_vejez, sheet_name='B-2020, Mujeres', skiprows=6, index_col='Edad'
        )
        
        # 2. Cargar Invalidez
        df_h_inv = pd.read_excel(
            arch_h_inv, sheet_name='MI-2020, Hombres', skiprows=6, index_col='Edad'
        )
        df_m_inv = pd.read_excel(
            arch_m_inv, sheet_name='MI-2020, Mujeres', skiprows=6, index_col='Edad'
        )

        # 3. Crear el diccionario anidado
        # (1 - qx) es la probabilidad de supervivencia
        tablas_anidadas = {
            'Vejez': {
                'Hombre': (1 - df_h_vejez['Tasas de mortalidad qx']).to_dict(),
                'Mujer': (1 - df_m_vejez['Tasas de mortalidad qx']).to_dict()
            },
            'Invalidez': {
                'Hombre': (1 - df_h_inv['Tasas de mortalidad qx']).to_dict(),
                'Mujer': (1 - df_m_inv['Tasas de mortalidad qx']).to_dict()
            }
        }
        
        # 4. Regla especial: Beneficiarias no inválidas usan B-2020 (Vejez Mujer)
        tablas_anidadas['Beneficiaria'] = tablas_anidadas['Vejez']['Mujer']
        
        return tablas_anidadas
        
    except FileNotFoundError as e:
        st.error(f"Error: No se encontró un archivo de tabla de mortalidad. {e}")
        return None
    except Exception as e:
        st.error(f"Error al leer Excel. Revisa los nombres de las hojas. Error: {e}")
        return None

@st.cache_data
def cargar_vector_vtd(archivo_etti_cmf, hoja, col_mes, col_metrica):
    """
    Carga el Vector de Tasas de Descuento (VTD) V28.0
    Fuerza la lectura de todo como string (dtype=str) para
    evitar la conversión automática de 'oct-25' a Timestamp.
    """
    try:
        # --- INICIO PARCHE V27.0 ---
        df_etti_full = pd.read_excel(
            archivo_etti_cmf,
            sheet_name=hoja,
            skiprows=0, 
            header=[0, 1], 
            index_col=0, 
            dtype=str 
        )
        df_etti_full.index.name = "Plazo"
        
        df_etti_full.index = df_etti_full.index.astype(int)
        # --- FIN PARCHE V27.0 ---

        # --- Limpieza V24.2 ---
        level_0 = df_etti_full.columns.get_level_values(0)
        cleaned_level_0 = [col.strip() if isinstance(col, str) else col for col in level_0]
        
        level_1 = df_etti_full.columns.get_level_values(1)
        cleaned_level_1 = [col.strip() if isinstance(col, str) else col for col in level_1]
        
        df_etti_full.columns = pd.MultiIndex.from_arrays([cleaned_level_0, cleaned_level_1])
        # --- FIN LIMPIEZA ---

        vector_series = df_etti_full.loc[:, (col_mes, col_metrica)]

        vector_series = vector_series.str.replace('%', '', regex=False) \
                                     .str.replace(',', '.', regex=False) \
                                     .astype(float) / 100.0
            
        vector_series = vector_series.dropna()
        vtd_dict = vector_series.to_dict()

        max_plazo_cargado = max(vtd_dict.keys())
        tasa_largo_plazo = vtd_dict[max_plazo_cargado]
        
        for t in range(int(max_plazo_cargado) + 1, 111): # Rellenar hasta edad 110
            vtd_dict[t] = tasa_largo_plazo
            
        return vtd_dict

    # --- INICIO BLOQUE DEBUG V24.5 ---
    except KeyError:
        st.error(f"Error al leer VTD: No se encontró la columna '{col_mes}' / '{col_metrica}' en la hoja '{hoja}'.")
        st.error("¡MODO DEBUG! Nombres de columna leídos desde el Excel:")
        try:
            st.warning(df_etti_full.columns.to_list())
        except Exception as e_debug:
            st.error(f"Error durante el debug: {e_debug}")
        
        st.error("VERIFICA que los nombres en el script (líneas 207-209) coincidan 100% con lo que se muestra en la lista de arriba.")
        return None
    # --- FIN BLOQUE DEBUG V24.5 ---
        
    except FileNotFoundError:
        st.error(f"Error: No se encontró el archivo '{archivo_etti_cmf}'.")
        return None
    except Exception as e:
        st.error(f"Error al procesar el archivo VTD: {e}")
        return None

# --- INICIO FUNCIÓN V31.0 ---
@st.cache_data
def cargar_tasas_de_venta(archivo_tasas_venta):
    """
    Carga el archivo de Tasas de Venta Promedio (svtas_rv.xlsx)
    publicado por la CMF.
    """
    try:
        df_tasas = pd.read_excel(
            archivo_tasas_venta,
            sheet_name='Informe SVTAS', # <-- ¡CORRECCIÓN V31.0!
            skiprows=0, 
            index_col=0 
        )
        df_tasas.index = df_tasas.index.str.strip()
        df_tasas = df_tasas.replace({',': '.'}, regex=True).astype(float)
        
        return df_tasas
        
    except FileNotFoundError:
        st.error(f"Error: No se encontró el archivo '{archivo_tasas_venta}'.")
        return None
    except Exception as e:
        st.error(f"Error al procesar el archivo de Tasas de Venta: {e}")
        return None
# --- FIN FUNCIÓN V31.0 ---


def obtener_prob_supervivencia(sexo, edad, es_invalido, tablas_mortalidad):
    """
    Consulta las Tablas de Mortalidad Anidadas (V24.1).
    Selecciona la tabla correcta (Vejez o Invalidez) según el estado. (Pilar 2)
    """
    try:
        if es_invalido:
            # Si es inválido, usa la tabla de Invalidez (MI-2020)
            return tablas_mortalidad['Invalidez'][sexo][edad]
        else:
            # Si NO es inválido, usa la tabla de Vejez (CB/B-2020)
            return tablas_mortalidad['Vejez'][sexo][edad]
            
    except KeyError:
        return 0.0

# --- MOTOR 1 (V24.1): CÁLCULO VEJEZ / INVALIDEZ ---
def calcular_factores_combinados(
    datos_afiliado, # P2
    conyuge_data, hijos_data,
    vector_vtd, # P1
    tablas_mortalidad, 
    modo_calculo, # P1/P3
    tasa_plana_rp=0.0, # P1/P3
    periodo_garantizado_en_anos=0,
    anos_de_aumento=0
    ):
    """
    Motor Dual:
    - Si modo_calculo == 'RP' o 'TASA_PLANA': Usa tasa_plana_rp
    - Si modo_calculo == 'RVI': Usa vector_vtd
    Además, usa el estado 'es_invalido' de los datos (Pilar 2)
    """
    
    edad_maxima = 110
    factor_temporal = 0.0
    factor_diferido = 0.0

    # --- INICIO V33.0: Chequeo de seguridad para datos_afiliado ---
    # En modo Sobrevivencia, datos_afiliado es None. Este motor no debe ser llamado.
    if not datos_afiliado:
        st.error("Error Crítico: 'calcular_factores_combinados' fue llamado sin 'datos_afiliado'. Use 'calcular_factor_sobrevivencia'.")
        return 0.0, 0.0
    # --- FIN V33.0 ---

    prob_afiliado_vivo_acum = 1.0
    prob_conyuge_vivo_acum = 0.0
    if conyuge_data:
        prob_conyuge_vivo_acum = 1.0
    
    hijos_estado = []
    for hijo in hijos_data:
        hijos_estado.append({'datos': hijo, 'prob_vivo_acum': 1.0})

    for t in range(0, edad_maxima - datos_afiliado['edad'] + 1):
        if t > 0:
            # --- INICIO CAMBIO V24.1 (Pilar 2) ---
            prob_afiliado_vivo_acum *= obtener_prob_supervivencia(
                datos_afiliado['sexo'], 
                datos_afiliado['edad'] + t - 1, 
                datos_afiliado['es_invalido'], 
                tablas_mortalidad
            )
            
            if conyuge_data and (conyuge_data['edad'] + t - 1 < edad_maxima):
                prob_conyuge_vivo_acum *= obtener_prob_supervivencia(
                    conyuge_data['sexo'], 
                    conyuge_data['edad'] + t - 1, 
                    conyuge_data['es_invalido'], 
                    tablas_mortalidad
                )
            else:
                 prob_conyuge_vivo_acum = 0.0
            # --- FIN CAMBIO V24.1 ---
                
            for h_estado in hijos_estado:
                edad_actual_hijo = h_estado['datos']['edad'] + t
                if edad_actual_hijo - 1 < edad_maxima:
                    # Hijos se asumen no-inválidos (usan tabla Vejez)
                    h_estado['prob_vivo_acum'] *= obtener_prob_supervivencia(
                        h_estado['datos']['sexo'], edad_actual_hijo - 1, False, tablas_mortalidad
                    )
                else:
                    h_estado['prob_vivo_acum'] = 0.0
        
        prob_afiliado_vivo = prob_afiliado_vivo_acum
        prob_afiliado_muerto = 1.0 - prob_afiliado_vivo
        
        pago_estado_1_contingente = 1.0 * prob_afiliado_vivo
        
        pago_total_sobrevivencia = 0.0
        if conyuge_data:
            pago_total_sobrevivencia += conyuge_data['pct_pension'] * prob_conyuge_vivo_acum
        for h_estado in hijos_estado:
            edad_actual_hijo = h_estado['datos']['edad'] + t
            if edad_actual_hijo < h_estado['datos']['edad_limite']:
                pago_total_sobrevivencia += h_estado['datos']['pct_pension'] * h_estado['prob_vivo_acum']
        
        pago_total_sobrevivencia = min(pago_total_sobrevivencia, 1.0)
        pago_estado_2_contingente = pago_total_sobrevivencia * prob_afiliado_muerto
        
        pago_contingente_total = pago_estado_1_contingente + pago_estado_2_contingente
        
        pago_cierto = 0.0
        if t < periodo_garantizado_en_anos:
            pago_cierto = 1.0
            
        pago_base_del_ano_t = max(pago_contingente_total, pago_cierto)
        
        # --- INICIO CAMBIO V30.0 (Descuento Dual) ---
        factor_descuento = 0.0
        if t == 0:
            factor_descuento = 1.0 # Pago hoy
        
        elif modo_calculo == 'RVI':
            # MODO RVI: Usa el Vector VTD
            tasa_para_plazo_t = vector_vtd.get(t, vector_vtd[110]) # Fallback a 110
            factor_descuento = (1 / (1 + tasa_para_plazo_t)) ** t
        
        # Modo RP o Tasa de Venta (ambos usan tasa plana)
        elif modo_calculo == 'RP' or modo_calculo == 'TASA_PLANA':
            # MODO RP: Usa la Tasa Plana (TITRP o Tasa de Venta)
            v_rp = 1 / (1 + tasa_plana_rp)
            factor_descuento = v_rp ** t

        vp_pago = factor_descuento * pago_base_del_ano_t
        # --- FIN CAMBIO V30.0 ---
        
        if t < anos_de_aumento:
            factor_temporal += vp_pago
        else:
            factor_diferido += vp_pago
    
    return factor_temporal, factor_diferido

# --- ¡¡NUEVA FUNCIÓN V32.0!! ---
# --- MOTOR 2: CÁLCULO DE SOBREVIVENCIA ---
def calcular_factor_sobrevivencia(
    conyuge_data, 
    hijos_data,
    vector_vtd, 
    tablas_mortalidad, 
    modo_calculo, 
    tasa_plana_rv=0.0,
    edad_maxima=110
    ):
    """
    Calcula el Factor Actuarial para una Renta Vitalicia de Sobrevivencia.
    El Afiliado/Causante se asume fallecido (prob_muerto = 1.0 desde t=0).
    El factor representa el costo (Prima) de pagar 1 UF de Pensión de Referencia.
    """
    
    factor_total = 0.0

    # 1. Inicializar estados de supervivencia de beneficiarios
    prob_conyuge_vivo_acum = 0.0
    if conyuge_data:
        prob_conyuge_vivo_acum = 1.0

    hijos_estado = []
    for hijo in hijos_data:
        hijos_estado.append({'datos': hijo, 'prob_vivo_acum': 1.0})

    # 2. Bucle de cálculo (Afiliado no participa)
    # Se calcula para cada año futuro (t)
    for t in range(0, edad_maxima + 1):
        
        if t > 0:
            # 2.1. Actualizar Supervivencia de Beneficiarios
            if conyuge_data and (conyuge_data['edad'] + t - 1 < edad_maxima):
                prob_conyuge_vivo_acum *= obtener_prob_supervivencia(
                    conyuge_data['sexo'], 
                    conyuge_data['edad'] + t - 1, 
                    conyuge_data['es_invalido'], 
                    tablas_mortalidad
                )
            else:
                prob_conyuge_vivo_acum = 0.0 # Asegura que sea 0 si supera la edad max
            
            for h_estado in hijos_estado:
                edad_actual_hijo = h_estado['datos']['edad'] + t
                if edad_actual_hijo - 1 < edad_maxima:
                    # Hijos usan tabla de Vejez (no inválidos por defecto)
                    h_estado['prob_vivo_acum'] *= obtener_prob_supervivencia(
                        h_estado['datos']['sexo'], edad_actual_hijo - 1, False, tablas_mortalidad
                    )
                else:
                    h_estado['prob_vivo_acum'] = 0.0

        # 2.2. Calcular Pago Contingente Total (como % de la Pensión de Referencia)
        # (Esto es el 'pago_estado_2' de tu otro motor)
        pago_total_sobrevivencia_pct = 0.0
        
        if conyuge_data:
            # Suma el % del cónyuge si está vivo
            pago_total_sobrevivencia_pct += conyuge_data['pct_pension'] * prob_conyuge_vivo_acum

        for h_estado in hijos_estado:
            edad_actual_hijo = h_estado['datos']['edad'] + t
            # Suma el % del hijo SI está vivo Y es menor a su edad límite
            if edad_actual_hijo < h_estado['datos']['edad_limite']:
                pago_total_sobrevivencia_pct += h_estado['datos']['pct_pension'] * h_estado['prob_vivo_acum']

        # 2.3. Aplicar el TOPE Legal (100% de la Pensión de Referencia)
        pago_base_del_ano_t = min(pago_total_sobrevivencia_pct, 1.0)
        
        # 2.4. Aplicar Descuento (Lógica V30.0 copiada)
        factor_descuento = 0.0
        if t == 0:
            factor_descuento = 1.0 # Pago hoy
        
        elif modo_calculo == 'RVI':
            # MODO RVI: Usa el Vector VTD
            tasa_para_plazo_t = vector_vtd.get(t, vector_vtd[110]) # Fallback a 110
            factor_descuento = (1 / (1 + tasa_para_plazo_t)) ** t
        
        elif modo_calculo == 'TASA_PLANA':
            # MODO Tasa de Venta: Usa la Tasa Plana
            v_rv = 1 / (1 + tasa_plana_rv)
            factor_descuento = v_rv ** t

        vp_pago = factor_descuento * pago_base_del_ano_t
        
        # 2.5. Acumular Factor
        factor_total += vp_pago

    return factor_total

# --- FUNCIÓN AYUDANTE PARA CLP (V8.0) ---
def calcular_descuentos_clp(pension_uf, valor_uf):
    """
    Calcula los montos en pesos, el descuento de salud y el líquido.
    """
    pension_bruta_clp = pension_uf * valor_uf
    descuento_salud_clp = pension_bruta_clp * 0.07 # 7% de descuento
    pension_liquida_clp = pension_bruta_clp - descuento_salud_clp
    return pension_bruta_clp, descuento_salud_clp, pension_liquida_clp

# --- ¡FUNCIÓN V20.0: CONSTRUCTOR DE PDF NATIVO! (MODIFICADA V34.0) ---
def create_native_pdf_report(data):
    """
    Usa fpdf2 NATIVAMENTE para construir un PDF limpio y profesional.
    (Versión modificada V34.0).
    """
    pdf = FPDF()
    pdf.add_page()
    
    # --- Configuración de Fuentes ---
    pdf.set_font("Times", "B", 15) # Título H1
    
    # --- Cabecera del Reporte ---
    pdf.cell(0, 10, "ESTUDIO PRELIMINAR DE PENSIÓN", ln=1, align="C")
    pdf.set_font("Times", "B", 13) # Título H2
    pdf.cell(0, 10, f"SR. {data['input_afiliado_nombre'].upper()}", ln=1, align="C")
    pdf.ln(5) # Salto de línea
    
    # --- Datos del Afiliado (MODIFICADO V32.0) ---
    pdf.set_font("Times", "", 10)
    pdf.cell(0, 5, f"Valor UF Utilizado: ${data['input_valor_uf_clp']:,.0f}".replace(",", "."), ln=1)
    
    # Mostrar datos del afiliado solo si NO es Sobrevivencia
    if not data.get('es_sobrevivencia', False):
        pdf.cell(0, 5, f"Edad Afiliado: {data['afiliado_edad_calculada']} años ({data['afiliado_tipo_pension']})", ln=1)
    
    if data['incluye_conyuge']:
        tipo_conyuge = "Inválido" if data['datos_conyuge']['es_invalido'] else ""
        pdf.cell(0, 5, f"Beneficiario Conyuge {data['datos_conyuge']['edad']} años {tipo_conyuge}", ln=1)
    
    pdf.cell(0, 5, f"Saldo Acumulado (Bruto): {data['saldo_uf']:,.0f} UF".replace(",", "."), ln=1)

    # --- INICIO CAMBIO V24.1 (Pilar 3) ---
    if data['check_incluye_comision']:
        pdf.set_font("Times", "I", 9) # Fuente más pequeña e itálica
        pdf.set_text_color(85, 85, 85) # Gris
        pdf.cell(0, 5, 
            f"(Se descuenta {data['input_comision_pct']:.2f}% de comisión. Prima Neta RVI: {data['prima_neta_rvi']:,.0f} UF)"
            .replace(",", "."), ln=1)
        pdf.set_font("Times", "", 10) # Reset
        pdf.set_text_color(0, 0, 0) # Reset
    # --- FIN CAMBIO V24.1 ---
    pdf.ln(5)

    # --- Función Ayudante para dibujar Tablas (MODIFICADA V34.0) ---
    def draw_table(title, subtitle, data_rows, column_config):
        pdf.set_font("Times", "B", 11) # Título H3
        if title:
            pdf.cell(0, 10, title, ln=1)
        
        if subtitle:
            pdf.set_font("Times", "I", 10)
            pdf.set_text_color(85, 85, 85) # Gris
            pdf.cell(0, 5, subtitle, ln=1, align="L")
            pdf.set_text_color(0, 0, 0) # Reset color
            pdf.ln(2)
        
        pdf.set_font("Times", "B", 9)
        pdf.set_fill_color(242, 242, 242) # Gris claro
        for col_name, col_width in column_config:
            pdf.cell(col_width, 7, col_name, border=1, ln=0, align="C", fill=True)
        pdf.ln()
        
        pdf.set_font("Times", "", 9)
        for row in data_rows:
            is_bonus_row = row.get("is_bonus_row", False)
            is_sub_row = row.get("is_sub_row", False) 
            
            # Dibujar cada celda
            for header_name, col_width in column_config:
                
                data_key = header_name
                if header_name.startswith("Desc.") and header_name != "Dscto. 7% Salud":
                    data_key = "Comisión AFP"

                val = row.get(data_key, "")
                
                # --- Formateo de texto ---
                if isinstance(val, float) and data_key.endswith("(UF)"):
                    text = f"{val:,.2f} UF"
                # --- INICIO V34.0 ---
                elif isinstance(val, float) and data_key == "Tasa (%)":
                    text = f"{val:,.2f}%"
                # --- FIN V34.0 ---
                elif isinstance(val, float) and (data_key == "Dscto. 7% Salud" or data_key == "Comisión AFP"):
                    text = f"-{val:,.0f}" # Formato como negativo
                elif isinstance(val, float):
                    text = f"${val:,.0f}" # Formato para Bruto/Líquido
                else:
                    text = str(val)
                
                # --- Alineación y Bordes (MODIFICADO V23.2) ---
                align = "L"
                border = 1
                
                if data_key == "Tasa (%)" or data_key.endswith("(UF)"): # Centrar tasas y UF
                    align = "C"

                if is_bonus_row:
                    if data_key == "Modalidad":
                        align = "R"
                        border = "LBR"
                    elif data_key == "Pensión Liquida":
                        align = "L"
                        border = "RBL"
                    else:
                        text = ""
                        border = "B" 
                elif is_sub_row:
                    if data_key == "Modalidad":
                        align = "L"
                        border = "LR" 
                    else:
                        text = ""
                        border = "R" 
                
                pdf.cell(col_width, 7, text, border=border, ln=0, align=align)
            pdf.ln()

    # --- TABLA 1: Retiro Programado (¡¡MODIFICADA V23.4!!) ---
    if data['rp_rows']:
        com_header = data.get('comision_header_str', 'Comisión AFP')
        # Total width: 55+25+30+20+30+30 = 190
        col_config_rp = [
            ("Modalidad", 55), ("Pensión (UF)", 25), ("Pensión M. Bruto", 30),
            (com_header, 20), 
            ("Dscto. 7% Salud", 30), 
            ("Pensión Liquida", 30)
        ]
        draw_table("1. Retiro Programado", data.get('afp_details_str', ''), data['rp_rows'], col_config_rp)
        pdf.ln(5)

    # --- TABLA 2: RVI Simple y Garantizada (¡¡MODIFICADA V34.0!!) ---
    if data['rvi_simple_rows']:
        # Total width: 60+20+25+30+30+25 = 190
        col_config_rvi = [
            ("Modalidad", 60), 
            ("Tasa (%)", 20), # <-- NUEVA COLUMNA V34.0
            ("Pensión (UF)", 25), 
            ("Pensión M. Bruto", 30),
            ("Dscto. 7% Salud", 30), # <-- Ancho ajustado
            ("Pensión Liquida", 25)  # <-- Ancho ajustado
        ]

        # --- INICIO CAMBIO V32.0 ---
        subtitle_rvi = f"Cálculo RVI: {data['metodo_rvi_desc']}"
        title_rvi = "2. Renta Vitalicia Inmediata (Simple y Garantizada)"
        if data.get('es_sobrevivencia', False):
             title_rvi = "2. Pensiones de Sobrevivencia"
        # --- FIN CAMBIO V32.0 ---
        
        draw_table(title_rvi, subtitle_rvi, data['rvi_simple_rows'], col_config_rvi)
        pdf.ln(5)

    # --- TABLA 3: RVI con Aumento Temporal (¡¡MODIFICADA V23.4!!) ---
    if data['rvat_rows']:
        # Total width: 70+25+30+35+30 = 190
        col_config_rvat = [
            ("Modalidad", 70), ("Pensión (UF)", 25), ("Pensión M. Bruto", 30),
            ("Dscto. 7% Salud", 35), ("Pensión Liquida", 30)
        ]
        draw_table("3. Renta Vitalicia con Aumento Temporal", "", data['rvat_rows'], col_config_rvat)
        pdf.ln(5)
    
    # --- TABLA 4: RP con RVD (NUEVO V33.0) ---
    if data['rvd_rows']:
        # Usamos la misma config que RP, ya que tiene la comisión
        com_header_rvd = data.get('comision_header_str', 'Comisión AFP')
        col_config_rvd = [
            ("Modalidad", 55), ("Pensión (UF)", 25), ("Pensión M. Bruto", 30),
            (com_header_rvd, 20), 
            ("Dscto. 7% Salud", 30), 
            ("Pensión Liquida", 30)
        ]
        
        # Subtítulo (usa el de RVI ya que depende del mismo cálculo)
        subtitle_rvd = f"Cálculo RVI: {data['metodo_rvi_desc']}"
        
        draw_table("4. RP con Renta Vitalicia Diferida", subtitle_rvd, data['rvd_rows'], col_config_rvd)
        pdf.ln(5)


    # --- Pie de Página del Reporte ---
    pdf.set_font("Times", "I", 8)
    pdf.set_text_color(85, 85, 85)
    pdf.cell(0, 5, "NOTA: VALORES ESTIMATIVOS NO CONSTITUYEN UNA OFERTA FORMAL DE PENSIÓN.", ln=1)
    pdf.cell(0, 5, "LA PGU SE SOLICITA A LOS 65 AÑOS, REQUISITO TENER REGISTRO SOCIAL DE HOGARES Y NO PERTENECER AL 90% DE MAYORES INGRESOS.", ln=1)
    pdf.cell(0, 5, "BONIFICACIÓN POR AÑO COTIZADO SE COMIENZA A PAGAR A LOS 9 MESES DE PUBLICADA LA LEY. LA BONIFICACIÓN SON 0.1 UF POR AÑO COTIZADO...", ln=1)
    
    return bytes(pdf.output())


# --- 3. LA INTERFAZ WEB ---

st.title("🤖 Calculadora de Pensiones 34.0") # Título actualizado
st.subheader("Centro de Cotizaciones y Generador de Informes")

# --- Nombres de archivos Excel ---

# Pilar 2: Tablas de Mortalidad (4 tablas)
ARCHIVO_H_VEJEZ = 'CB-H-2020.xlsx'
ARCHIVO_M_VEJEZ = 'B-M-2020.xlsx'
ARCHIVO_H_INV = 'I-H-2020.xlsx'
ARCHIVO_M_INV = 'I-M-2020.xlsx'

TABLAS_DE_MORTALIDAD_REALES = cargar_tablas_de_mortalidad_reales(
    ARCHIVO_H_VEJEZ, ARCHIVO_M_VEJEZ, ARCHIVO_H_INV, ARCHIVO_M_INV
)
if not TABLAS_DE_MORTALIDAD_REALES:
    st.stop()

# --- INICIO PILAR 1 (VTD) V28.0 ---
ARCHIVO_ETTI = 'VTD 2020-2025.xlsx' 

HOJA_VTD = 'SR 2025' 
COL_MES_VTD = 'oct-25'
COL_METRICA_VTD = 'Spot Rate' 

VECTOR_VTD = cargar_vector_vtd(
    ARCHIVO_ETTI, 
    hoja=HOJA_VTD, 
    col_mes=COL_MES_VTD, 
    col_metrica=COL_METRICA_VTD
)
if not VECTOR_VTD:
    st.error("Falla crítica: No se pudo cargar el Vector de Tasas de Descuento (VTD).")
    st.stop()
else:
    vtd_details_str = f"VTD Cargado: {COL_MES_VTD} (Hoja {HOJA_VTD})"
# --- FIN PILAR 1 V28.0 ---

# --- INICIO CARGA V30.0 (TASAS DE VENTA) ---
ARCHIVO_TASAS_VENTA = 'svtas_rv.xlsx'
DF_TASAS_VENTA = cargar_tasas_de_venta(ARCHIVO_TASAS_VENTA)
if DF_TASAS_VENTA is None:
    st.error("Falla crítica: No se pudo cargar el archivo de Tasas de Venta (svtas_rv.xlsx).")
    st.stop()
# --- FIN CARGA V30.0 ---


# --- Diccionario de Comisiones AFP ---
AFP_COMMISSIONS = {
    "AFP PLANVITAL": 0.00,
    "AFP HABITAT": 0.95,
    "AFP CAPITAL": 1.25,
    "AFP CUPRUM": 1.25,
    "AFP MODELO": 1.20,
    "AFP PROVIDA": 1.25,
    "AFP UNO": 1.20,
}

# --- Panel Lateral de ENTRADA DE DATOS (¡¡MODIFICADA V34.0!!) ---
with st.sidebar:
    st.header("Parámetros Globales")
    
    input_afiliado_nombre = st.text_input("Nombre Afiliado", "GODOFREDO VERA VERA")
    
    input_valor_uf_clp = st.number_input(
        "Valor UF ($)", min_value=30000, value=39600, step=1
    )
    
    saldo_uf = st.number_input(
        "Saldo Acumulado (UF)", min_value=100, value=4500
    )
    
    st.subheader("Configuración Retiro Programado")
    input_afp_nombre = st.selectbox(
        "AFP (para Retiro Programado)",
        options=list(AFP_COMMISSIONS.keys()),
        index=1 # Default en Habitat
    )
    
    input_tasa_rp = st.number_input(
        "Tasa RP (TITRP %)", min_value=1.0, max_value=10.0, value=3.41, step=0.01, format="%.2f"
    )
    
    # --- INICIO CAMBIO V30.0 (Selector de Método) ---
    st.subheader("Configuración Renta Vitalicia")
    
    input_metodo_rvi = st.radio(
        "Método de Cálculo RVI",
        ["Tasa de Venta (Promedio Mercado)", "Vector de Descuento (Tarificador CMF)"],
        index=0,
        help="Elige cómo calcular la RVI. 'Tasa de Venta' usa la tasa promedio publicada por la CMF. 'Vector de Descuento' usa el VTD para un cálculo actuarial."
    )
    
    # --- INICIO CAMBIO V34.0 ---
    input_cia_rvi = None
    check_comparar_todas = False # V34.0: Inicializar
    
    if input_metodo_rvi == "Tasa de Venta (Promedio Mercado)":
        
        check_comparar_todas = st.checkbox(
            "Comparar todas las Compañías (RVI Simple)",
            help="Calcula la RVI Simple para todas las Cías. del archivo 'svtas_rv.xlsx' y las ordena de mayor a menor."
        )
        
        if check_comparar_todas:
            # Si compara todas, forzamos "Media Mercado" para los escenarios complejos (A,B,C y RVD)
            # para no saturar el informe. La comparación se hará solo en la Tabla 2.
            input_cia_rvi = "Media Mercado"
            st.caption("Se usarán todas las Cías. para RVI Simple (Tabla 2). Se usará 'Media Mercado' para los demás escenarios (A, B, C, RVD).")
        else:
            # Comportamiento original V33.0
            lista_cias = ['Media Mercado'] + list(DF_TASAS_VENTA.index.drop('Media Mercado'))
            input_cia_rvi = st.selectbox(
                "Selecciona Compañía (para Tasa de Venta)",
                options=lista_cias
            )
    # --- FIN CAMBIO V34.0 ---
    
    else:
        st.caption(vtd_details_str) # Muestra el VTD cargado solo si se usa
    
    check_incluye_comision = st.checkbox("Ajustar por Comisión de Intermediación")
    
    input_comision_pct = 0.0
    if check_incluye_comision:
        input_comision_pct = st.number_input(
            "Comisión Asesor Previsional (%)",
            min_value=0.0, max_value=5.0, value=1.2, step=0.1, format="%.2f",
            help="Porcentaje del saldo bruto (legalmente topado) que se paga al asesor."
        )
    # --- FIN CAMBIO V30.0 ---

    st.subheader("Configuración Adicionales")
    input_valor_pgu_clp = st.number_input(
        "Valor PGU ($)", min_value=0, value=224004, step=1, help="Monto de la PGU a sumar."
    )
    
    check_incluye_pgu = st.checkbox("Incluir PGU")
    check_incluye_bono = st.checkbox("Incluir Bonificación Adicional")
    
    input_bonificacion_uf = 0.0
    if check_incluye_bono:
        input_bonificacion_uf = st.number_input(
            "UF Bonificación Adicional", min_value=0.0, max_value=3.0, value=2.5, step=0.1, format="%.2f",
            help="Monto en UF de la Bonificación Adicional (ej. 2.0, 2.5)."
        )

    # --- INICIO CAMBIO V32.0 (Nuevos Tipos de Pensión) ---
    st.subheader("Datos del Cálculo")
    
    afiliado_tipo_pension = st.selectbox(
        "Tipo de Pensión", 
        ['Vejez (Edad Legal)', 'Vejez Anticipada', 'Invalidez', 'Sobrevivencia']
    )

    input_pension_referencia_uf = 0.0
    input_promedio_10_anos_uf = 0.0

    if afiliado_tipo_pension == 'Sobrevivencia':
        st.info("MODO SOBREVIVENCIA: El 'Afiliado' es el Causante (fallecido). Ingrese solo los datos de los Beneficiarios.")
        # Ocultar inputs de afiliado que no se usarán
        afiliado_dob = date(1900, 1, 1) # Valor placeholder
        afiliado_sexo = 'Hombre' # Valor placeholder
        afiliado_edad_calculada = 0
        datos_afiliado = None # ¡Clave! El afiliado no participa
        
        input_pension_referencia_uf = st.number_input(
            "Pensión de Referencia (UF)", 
            min_value=1.0, value=20.0, step=0.5,
            help="La Pensión de Referencia (PR) sobre la cual se calculan los porcentajes de los beneficiarios. Ej: 70% del IBL del causante."
        )

    else:
        # Mostrarlos solo si NO es Sobrevivencia
        st.markdown("**Datos del Afiliado**")
        afiliado_dob = st.date_input(
            "Fecha de Nac. Afiliado",
            min_value=date(1920, 1, 1),
            max_value=date.today(),
            value=date(1959, 11, 8) 
        )
        afiliado_sexo = st.selectbox("Sexo Afiliado", ['Hombre', 'Mujer'])
        afiliado_edad_calculada = calculate_age(afiliado_dob)
        st.caption(f"Edad calculada: {afiliado_edad_calculada} años")
        
        datos_afiliado = {
            'edad': afiliado_edad_calculada,
            'sexo': afiliado_sexo,
            'es_invalido': (afiliado_tipo_pension == 'Invalidez')
            # Nota: 'Vejez Anticipada' usa la misma tabla que 'Vejez (Edad Legal)'
        }

        if afiliado_tipo_pension == 'Vejez Anticipada':
            input_promedio_10_anos_uf = st.number_input(
                "Promedio Imponible 10 Años (UF)", 
                min_value=1.0, value=25.0, step=0.5,
                help="El promedio de las remuneraciones imponibles de los últimos 10 años, en UF."
            )
            st.caption("Requisito: La pensión debe ser >= 80% de este promedio.")
    # --- FIN CAMBIO V32.0 ---

    st.subheader("Beneficiarios")
    incluye_conyuge = st.checkbox("Incluir Cónyuge Beneficiario")
    datos_conyuge = None
    if incluye_conyuge:
        conyuge_dob = st.date_input(
            "Fecha de Nac. Cónyuge",
            min_value=date(1920, 1, 1),
            max_value=date.today(),
            value=date(1963, 11, 8) # Default 62 años (aprox)
        )
        conyuge_sexo = st.selectbox("Sexo Cónyuge", ['Hombre', 'Mujer'])
        
        conyuge_es_invalido = st.checkbox("¿Cónyuge es beneficiario por invalidez?")
        
        conyuge_edad_calculada = calculate_age(conyuge_dob)
        st.caption(f"Edad cónyuge calculada: {conyuge_edad_calculada} años")
        
        datos_conyuge = {
            'edad': conyuge_edad_calculada,
            'sexo': conyuge_sexo, 
            'pct_pension': 0.60,
            'es_invalido': conyuge_es_invalido
        }

    datos_hijos = []
    num_hijos = st.number_input("Número de Hijos (menores de 18/24)", min_value=0, max_value=10, step=1)
    for i in range(num_hijos):
        st.markdown(f"**Hijo {i+1}**")
        h_dob = st.date_input(
            f"Fecha de Nac. Hijo {i+1}",
            min_value=date(1995, 1, 1),
            max_value=date.today(),
            value=date(2010, 1, 1),
            key=f"dob_h_{i}"
        )
        h_sexo = st.selectbox(f"Sexo Hijo {i+1}", ['Hombre', 'Mujer'], key=f"sexo_h_{i}")
        h_limite = st.selectbox(f"Límite Hijo {i+1} (18 o 24)", [18, 24], index=1, key=f"limite_h_{i}")
        h_edad_calculada = calculate_age(h_dob)
        st.caption(f"Edad hijo {i+1} calculada: {h_edad_calculada} años")
        
        datos_hijos.append({
            'edad': h_edad_calculada,
            'sexo': h_sexo,
            'pct_pension': 0.15,
            'edad_limite': h_limite
        })
    
    # --- Constructor de Escenarios V9.0 ---
    st.header("Centro de Cotizaciones")
    st.info("Selecciona los escenarios a comparar:")
    
    check_rp = st.checkbox("1. Retiro Programado (RP)", value=True)
    check_rvi_simple = st.checkbox("2. RVI Simple", value=True)
    st.markdown("---")
    st.subheader("Escenarios Personalizados")
    
    # --- Escenario A ---
    with st.expander("Configurar Escenario A"):
        check_esc_a = st.checkbox("Activar Escenario A")
        a_pg_anos = st.slider(
            "Años P.G. (A) (0=Sin PG)", 0, 25, 10, 5, key="a_pg", help="Período Garantizado en años. 120 meses = 10 años."
        )
        a_pct_aum = st.slider(
            "% Aumento (A) (0=Sin Aumento)", 0, 100, 0, 10, key="a_pct"
        )
        a_anos_aum = st.slider(
            "Años Aumento (A)", 1, 25, 1, 1, key="a_anos"
        )
    # --- Escenario B ---
    with st.expander("Configurar Escenario B"):
        check_esc_b = st.checkbox("Activar Escenario B")
        b_pg_anos = st.slider(
            "Años P.G. (B) (0=Sin PG)", 0, 25, 15, 5, key="b_pg"
        )
        b_pct_aum = st.slider(
            "% Aumento (B) (0=Sin Aumento)", 0, 100, 50, 10, key="b_pct"
        )
        b_anos_aum = st.slider(
            "Años Aumento (B)", 1, 25, 2, 1, key="b_anos"
        )
    # --- Escenario C ---
    with st.expander("Configurar Escenario C"):
        check_esc_c = st.checkbox("Activar Escenario C")
        c_pg_anos = st.slider(
            "Años P.G. (C) (0=Sin PG)", 0, 25, 20, 5, key="c_pg"
        )
        c_pct_aum = st.slider(
            "% Aumento (C) (0=Sin Aumento)", 0, 100, 100, 10, key="c_pct"
        )
        c_anos_aum = st.slider(
            "Años Aumento (C)", 1, 25, 3, 1, key="c_anos"
        )
    
    # --- INICIO CAMBIO V33.0 (RP-RVD) ---
    st.markdown("---")
    st.subheader("Modalidad Híbrida")
    with st.expander("Configurar RP con RVD"):
        check_rp_rvd = st.checkbox("Activar Escenario RP-RVD")
        n_anos_diferimiento = st.slider(
            "Años de RP (Diferimiento RVD)", 
            min_value=1, max_value=10, value=3, step=1, 
            key="n_rvd",
            help="Número de años que el afiliado estará en Retiro Programado antes de que comience la Renta Vitalicia Diferida."
        )
    # --- FIN CAMBIO V33.0 ---


# --- 4. EL BOTÓN DE CÁLCULO Y LOS RESULTADOS (¡¡REFACTORIZADO V34.0!!) ---

# Inicializa el estado para el reporte
if 'report_generated' not in st.session_state:
    st.session_state.report_generated = False
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None
if 'report_data' not in st.session_state:
    st.session_state.report_data = {}


if st.button("Generar Informe Comparativo", key="generar_informe"):
    
    # --- Lógica Común de Primas y Tasas (V31.0) ---
    tasa_rp_decimal = input_tasa_rp / 100.0
    
    comision_decimal = 0.0
    if check_incluye_comision:
        comision_decimal = input_comision_pct / 100.0

    prima_neta_rp = saldo_uf 
    prima_neta_rvi = saldo_uf * (1 - comision_decimal)
    
    # Inicializar listas
    rp_rows = []
    rvi_simple_rows = []
    rvat_rows = []
    rvd_rows = [] # <-- AÑADIDO V33.0
    
    afp_details_str = ""
    comision_header_str = ""

    # --- Lógica PGU/Bono (V29.0 - Sin cambios) ---
    bonificacion_clp = 0.0
    valor_pgu_a_sumar = 0.0
    texto_adicional = [] 
    
    if check_incluye_pgu:
        valor_pgu_a_sumar = input_valor_pgu_clp
        texto_adicional.append(f"PGU (${input_valor_pgu_clp:,.0f})")
        
    if check_incluye_bono:
        bonificacion_clp = input_bonificacion_uf * input_valor_uf_clp
        texto_adicional.append("Bonificación")
    
    pgu_texto_simple = ""
    pgu_texto_base = ""
    
    if texto_adicional:
        pgu_texto_simple = f" Pension + {' + '.join(texto_adicional)}" 
        pgu_texto_base = f" Pension + {' + '.join(texto_adicional)}" 
    
    
    # --- Lógica de Selección de Motor RVI (V30.0 - Sin cambios) ---
    metodo_rvi_desc = "" 
    tasa_plana_rvi_final = 0.0 
    modo_calculo_rvi_final = "" 
    
    if input_metodo_rvi == "Tasa de Venta (Promedio Mercado)":
        
        # --- INICIO CAMBIO V34.0 ---
        # Determinar la columna a usar (Vejez o Invalidez)
        # Esta se usará para el 'input_cia_rvi' (Media Mercado o una Cía. específica)
        columna_tasa = 'Vejez' # Default
        if afiliado_tipo_pension == 'Invalidez':
                 columna_tasa = 'Invalidez total' # Mapeo
        # --- FIN CAMBIO V34.0 ---
        
        try:
            # input_cia_rvi se define en el sidebar (V34.0)
            tasa_cia_pct = DF_TASAS_VENTA.loc[input_cia_rvi, columna_tasa]
            tasa_plana_rvi_final = tasa_cia_pct / 100.0
            modo_calculo_rvi_final = 'TASA_PLANA' # Usará el motor de tasa plana
            
            # La descripción dependerá de si se comparan todas o no
            if check_comparar_todas:
                 metodo_rvi_desc = f"Tasa Venta: Comparador (Base Escenarios: {input_cia_rvi} {tasa_cia_pct}%)"
            else:
                 metodo_rvi_desc = f"Tasa de Venta: {input_cia_rvi} ({columna_tasa}: {tasa_cia_pct}%)"

        except KeyError:
            st.error(f"No se encontró la tasa para {input_cia_rvi} / {columna_tasa}")
            st.stop()
            
    else: # "Vector de Descuento (Tarificador CMF)"
        modo_calculo_rvi_final = 'RVI' # Usará el motor VTD
        tasa_plana_rvi_final = 0.0 # No se usa
        metodo_rvi_desc = f"Vector de Descuento (VTD: {COL_MES_VTD})"
        
    # --- ¡¡INICIO REFACTOR V32.0: BIFURCACIÓN DE LÓGICA!! ---

    # Si NO hay beneficiarios, el modo Sobrevivencia no tiene sentido.
    if afiliado_tipo_pension == 'Sobrevivencia' and not incluye_conyuge and num_hijos == 0:
        st.error("Error en modo Sobrevivencia: Debe ingresar al menos un beneficiario (Cónyuge o Hijos).")
        st.stop()


    # --- RAMA 1: CÁLCULO DE SOBREVIVENCIA ---
    if afiliado_tipo_pension == 'Sobrevivencia':
        
        st.warning("MODO SOBREVIVENCIA: Los cálculos de Retiro Programado, Aumento Temporal y RP-RVD no aplican.")
        check_rp = False # Forzar a que no se calcule RP
        check_esc_a = check_esc_b = check_esc_c = False # No aplican escenarios
        check_rp_rvd = False # No aplica escenario híbrido
        
        # 1. Calcular el Factor de Costo
        factor_sobrevivencia = calcular_factor_sobrevivencia(
            datos_conyuge, datos_hijos,
            VECTOR_VTD,
            TABLAS_DE_MORTALIDAD_REALES,
            modo_calculo=modo_calculo_rvi_final,
            tasa_plana_rv=tasa_plana_rvi_final
        )

        if factor_sobrevivencia == 0:
            st.error("Error: El factor de sobrevivencia es cero. No se puede calcular la pensión.")
            st.stop()

        # 2. Calcular la Pensión de Referencia (PR) que el saldo puede financiar
        pension_ref_uf_financiable = (prima_neta_rvi / factor_sobrevivencia) / 12.0
        
        # 3. Determinar la PR Final a Pagar
        pension_ref_final_uf = 0.0
        if pension_ref_uf_financiable < input_pension_referencia_uf:
            pension_ref_final_uf = pension_ref_uf_financiable
            st.warning(f"Saldo Insuficiente: La PR legal ({input_pension_referencia_uf:.2f} UF) "
                       f"es mayor a la financiable ({pension_ref_uf_financiable:.2f} UF). "
                       "Se pagará la pensión financiable.")
        else:
            pension_ref_final_uf = input_pension_referencia_uf

        # 4. Poblar las filas del reporte (una fila por beneficiario)
        
        modalidad_sob_desc = "PENSIÓN SOBREVIVENCIA"
        tasa_usada_pct = None # V34.0
        
        if modo_calculo_rvi_final == 'TASA_PLANA':
            modalidad_sob_desc += f" ({input_cia_rvi})"
            col_tasa = 'Vejez' if afiliado_tipo_pension != 'Invalidez' else 'Invalidez total'
            tasa_usada_pct = DF_TASAS_VENTA.loc[input_cia_rvi, col_tasa]


        # Añadir Cónyuge al reporte
        if incluye_conyuge:
            pension_conyuge_uf = pension_ref_final_uf * datos_conyuge['pct_pension']
            bruto, dscto, liq = calcular_descuentos_clp(pension_conyuge_uf, input_valor_uf_clp)
            rvi_simple_rows.append({
                "Modalidad": f"{modalidad_sob_desc} (Cónyuge {datos_conyuge['pct_pension']*100:.0f}%)",
                "Tasa (%)": tasa_usada_pct, # V34.0
                "Pensión (UF)": pension_conyuge_uf,
                "Pensión M. Bruto": bruto, "Dscto. 7% Salud": dscto, "Pensión Liquida": liq
            })
            
        # Añadir Hijos al reporte
        for i, hijo_data in enumerate(datos_hijos):
            pension_hijo_uf = pension_ref_final_uf * hijo_data['pct_pension']
            bruto, dscto, liq = calcular_descuentos_clp(pension_hijo_uf, input_valor_uf_clp)
            rvi_simple_rows.append({
                "Modalidad": f"{modalidad_sob_desc} (Hijo {i+1} {hijo_data['pct_pension']*100:.0f}%)",
                "Tasa (%)": tasa_usada_pct, # V34.0
                "Pensión (UF)": pension_hijo_uf,
                "Pensión M. Bruto": bruto, "Dscto. 7% Salud": dscto, "Pensión Liquida": liq
            })


    # --- RAMA 2: CÁLCULO DE VEJEZ, V. ANTICIPADA E INVALIDEZ ---
    else:
        
        # --- NUEVO "GATEKEEPER" V32.0: VEJEZ ANTICIPADA ---
        if afiliado_tipo_pension == 'Vejez Anticipada':
            ft_temp, fd_temp = calcular_factores_combinados(
                datos_afiliado, datos_conyuge, datos_hijos,
                VECTOR_VTD, TABLAS_DE_MORTALIDAD_REALES,
                modo_calculo_rvi_final, tasa_plana_rvi_final, 0, 0
            )
            factor_total_temp = ft_temp + fd_temp
            if factor_total_temp == 0:
                st.error("Error de división por cero al verificar Vejez Anticipada.")
                st.stop()
            
            pension_verificacion_uf = (prima_neta_rvi / factor_total_temp) / 12.0
            pension_minima_requerida = input_promedio_10_anos_uf * 0.80
            
            if pension_verificacion_uf < pension_minima_requerida:
                st.error(f"AFILIADO NO CALIFICA PARA VEJEZ ANTICIPADA:")
                st.error(f"  - Pensión Calculada: {pension_verificacion_uf:,.2f} UF")
                st.error(f"  - Requisito (80% Promedio): {pension_minima_requerida:,.2f} UF")
                st.stop()
            else:
                st.success(f"Afiliado CALIFICA para Vejez Anticipada (Pensión {pension_verificacion_uf:,.2f} UF >= {pension_minima_requerida:,.2f} UF)")

        # --- Tarea 1: Retiro Programado (MODIFICADO V24.1) ---
        if check_rp:
            ft_rp, fd_rp = calcular_factores_combinados(
                datos_afiliado, 
                datos_conyuge, datos_hijos,
                None, # No usa VTD
                TABLAS_DE_MORTALIDAD_REALES,
                modo_calculo='RP', # Modo RP
                tasa_plana_rp=tasa_rp_decimal, # Tasa para RP
                periodo_garantizado_en_anos=0,
                anos_de_aumento=0
            )
            factor_total_rp = ft_rp + fd_rp
            
            pension_rp_uf_bruta = (prima_neta_rp / factor_total_rp) / 12.0
            
            comision_pct = AFP_COMMISSIONS.get(input_afp_nombre, 0.0) / 100.0
            comision_uf = pension_rp_uf_bruta * comision_pct
            pension_rp_uf_neta = pension_rp_uf_bruta - comision_uf
            
            bruto_clp, dscto_clp, liq_clp = calcular_descuentos_clp(pension_rp_uf_neta, input_valor_uf_clp)
            
            comision_clp = comision_uf * input_valor_uf_clp
            afp_details_str = f"({input_afp_nombre} - {comision_pct*100:.2f}%)"
            comision_header_str = f"Desc. {comision_pct*100:.2f}%"
            
            rp_rows.append({
                "Modalidad": "RETIRO PROGRAMADO",
                "Pensión (UF)": pension_rp_uf_neta,
                "Pensión M. Bruto": bruto_clp,
                "Comisión AFP": comision_clp, 
                "Dscto. 7% Salud": dscto_clp,
                "Pensión Liquida": liq_clp
            })
            
        # --- Función de ayuda para calcular RVI (MODIFICADA V30.0) ---
        def calcular_escenario_rvi(prima_a_usar, pg_anos, at_anos, pct_aumento):
            
            ft_rv, fd_rv = calcular_factores_combinados(
                datos_afiliado, 
                datos_conyuge, datos_hijos,
                VECTOR_VTD, 
                TABLAS_DE_MORTALIDAD_REALES,
                modo_calculo=modo_calculo_rvi_final, 
                tasa_plana_rp=tasa_plana_rvi_final, 
                periodo_garantizado_en_anos=pg_anos,
                anos_de_aumento=at_anos
            )
            
            pct_aumento_decimal = pct_aumento / 100.0
            denominador = (ft_rv * (1 + pct_aumento_decimal)) + fd_rv
            
            if denominador == 0: pension_anual_referencia = 0
            else: 
                pension_anual_referencia = prima_a_usar / denominador
            
            pension_anual_aumentada = pension_anual_referencia * (1 + pct_aumento_decimal)
            
            return {
                'p_ref_uf': pension_anual_referencia / 12.0,
                'p_aum_uf': pension_anual_aumentada / 12.0,
                'anos_aum': at_anos, 'pct_aum': pct_aumento,
                'pg_anos': pg_anos
            }

        # --- Tarea 2: RVI Simple (¡¡MODIFICADO V34.0!!) ---
        if check_rvi_simple:
            
            # --- INICIO BLOQUE V34.0 (Comparador) ---
            if input_metodo_rvi == "Tasa de Venta (Promedio Mercado)" and check_comparar_todas:
                st.info(f"Modo Comparación: Calculando RVI Simple para las {len(DF_TASAS_VENTA.index)} compañías.")
                
                # Determinar la columna a usar (Vejez o Invalidez)
                columna_tasa = 'Vejez' # Default
                if afiliado_tipo_pension == 'Invalidez':
                    columna_tasa = 'Invalidez total'
                
                resultados_comparacion = []

                # Iterar por cada compañía en el archivo de tasas
                for cia_nombre in DF_TASAS_VENTA.index:
                    try:
                        tasa_cia_pct = DF_TASAS_VENTA.loc[cia_nombre, columna_tasa]
                        tasa_plana_loop = tasa_cia_pct / 100.0

                        # 1. Calcular Factores (Motor 1) para esta Cía.
                        ft_rv, fd_rv = calcular_factores_combinados(
                            datos_afiliado, 
                            datos_conyuge, datos_hijos,
                            VECTOR_VTD, # Se pasa, pero el modo 'TASA_PLANA' lo ignora
                            TABLAS_DE_MORTALIDAD_REALES,
                            modo_calculo='TASA_PLANA', # Forzamos modo TASA_PLANA
                            tasa_plana_rp=tasa_plana_loop, # ¡Usamos la tasa del bucle!
                            periodo_garantizado_en_anos=0, # RVI Simple
                            anos_de_aumento=0 # RVI Simple
                        )
                        factor_total = ft_rv + fd_rv
                        if factor_total == 0: continue 

                        # 2. Calcular Pensión
                        pension_anual_ref = prima_neta_rvi / factor_total
                        pension_mensual_uf = pension_anual_ref / 12.0
                        
                        # 3. Calcular CLP
                        bruto, dscto, liq = calcular_descuentos_clp(pension_mensual_uf, input_valor_uf_clp)

                        # 4. Guardar resultado
                        resultados_comparacion.append({
                            "Modalidad": cia_nombre, # Nombre limpio de la Cía.
                            "Tasa (%)": tasa_cia_pct,
                            "Pensión (UF)": pension_mensual_uf,
                            "Pensión M. Bruto": bruto,
                            "Dscto. 7% Salud": dscto,
                            "Pensión Liquida": liq
                        })

                    except Exception as e:
                        st.warning(f"No se pudo calcular para {cia_nombre} (Tasa: {columna_tasa}): {e}")
                
                # 5. ¡ORDENAR! (De mayor a menor pensión)
                resultados_ordenados = sorted(resultados_comparacion, key=lambda x: x['Pensión (UF)'], reverse=True)
                
                # 6. Poblar rvi_simple_rows
                rvi_simple_rows.extend(resultados_ordenados) # Añadir todos los resultados

            else:
                # --- CÓDIGO V33.0 ORIGINAL (Si el comparador NO está activo) ---
                res = calcular_escenario_rvi(prima_neta_rvi, 0, 0, 0)
                bruto, dscto, liq = calcular_descuentos_clp(res['p_ref_uf'], input_valor_uf_clp)
                
                modalidad_simple_desc = "RVI SIMPLE"
                tasa_usada_pct = None
                
                if modo_calculo_rvi_final == 'TASA_PLANA':
                     modalidad_simple_desc += f" ({input_cia_rvi})"
                     # Buscamos la tasa que se usó
                     col_tasa = 'Vejez' if afiliado_tipo_pension != 'Invalidez' else 'Invalidez total'
                     tasa_usada_pct = DF_TASAS_VENTA.loc[input_cia_rvi, col_tasa]

                rvi_simple_rows.append({
                    "Modalidad": modalidad_simple_desc,
                    "Tasa (%)": tasa_usada_pct, # <-- AÑADIDO V34.0
                    "Pensión (UF)": res['p_ref_uf'],
                    "Pensión M. Bruto": bruto,
                    "Dscto. 7% Salud": dscto,
                    "Pensión Liquida": liq
                })
                
                # Lógica de PGU/Bono (sin cambios)
                if check_incluye_pgu or check_incluye_bono:
                    pgu_total_clp = liq + valor_pgu_a_sumar + bonificacion_clp
                    rvi_simple_rows.append({
                        "Modalidad": pgu_texto_simple,
                        "Pensión Liquida": pgu_total_clp,
                        "is_bonus_row": True
                    })
            # --- FIN BLOQUE V34.0 ---
        
        # --- Función para procesar escenarios (MODIFICADO V29.0) ---
        def procesar_escenario(check, pg_anos, at_anos, pct_aum, nombre_esc):
            if check:
                res = calcular_escenario_rvi(prima_neta_rvi, pg_anos, at_anos, pct_aum)
                if pct_aum == 0:
                    bruto, dscto, liq = calcular_descuentos_clp(res['p_ref_uf'], input_valor_uf_clp)
                    modalidad_nombre = f"{nombre_esc} (PG: {pg_anos}a)"
                    if pg_anos == 0: modalidad_nombre = f"{nombre_esc} (Simple)"
                    
                    rvi_simple_rows.append({
                        "Modalidad": modalidad_nombre,
                        "Pensión (UF)": res['p_ref_uf'],
                        "Pensión M. Bruto": bruto,
                        "Dscto. 7% Salud": dscto,
                        "Pensión Liquida": liq
                    })
                    
                    if check_incluye_pgu or check_incluye_bono:
                        pgu_total_clp = liq + valor_pgu_a_sumar + bonificacion_clp
                        rvi_simple_rows.append({
                            "Modalidad": pgu_texto_simple,
                            "Pensión Liquida": pgu_total_clp,
                            "is_bonus_row": True
                        })
                else:
                    bruto_ref, dscto_ref, liq_ref = calcular_descuentos_clp(res['p_ref_uf'], input_valor_uf_clp)
                    bruto_aum, dscto_aum, liq_aum = calcular_descuentos_clp(res['p_aum_uf'], input_valor_uf_clp)
                    
                    modalidad_texto_aumentado = f"R. V. Aumentado {at_anos * 12} meses - Garantizado {pg_anos * 12} meses."
                    rvat_rows.append({
                        "Modalidad": modalidad_texto_aumentado,
                        "Pensión (UF)": res['p_aum_uf'],
                        "Pensión M. Bruto": bruto_aum,
                        "Dscto. 7% Salud": dscto_aum,
                        "Pensión Liquida": liq_aum
                    })
                    
                    if check_incluye_pgu or check_incluye_bono:
                        pgu_total_clp_aumentada = liq_aum + valor_pgu_a_sumar + bonificacion_clp
                        rvat_rows.append({
                            "Modalidad": pgu_texto_base, 
                            "Pensión Liquida": pgu_total_clp_aumentada,
                            "is_bonus_row": True 
                        })
                    
                    rvat_rows.append({
                        "Modalidad": f" - P. BASE (desde mes {at_anos * 12 + 1}) Pension Definitiva",
                        "Pensión (UF)": res['p_ref_uf'],
                        "Pensión M. Bruto": bruto_ref,
                        "Dscto. 7% Salud": dscto_ref,
                        "Pensión Liquida": liq_ref
                    })
                    
                    if check_incluye_pgu or check_incluye_bono:
                        pgu_total_clp_base = liq_ref + valor_pgu_a_sumar + bonificacion_clp
                        rvat_rows.append({
                            "Modalidad": pgu_texto_base,
                            "Pensión Liquida": pgu_total_clp_base,
                            "is_bonus_row": True 
                        })
        
        # --- Tareas 3, 4, 5 (usando la nueva función) ---
        procesar_escenario(check_esc_a, a_pg_anos, a_anos_aum, a_pct_aum, "Escenario A")
        procesar_escenario(check_esc_b, b_pg_anos, b_anos_aum, b_pct_aum, "Escenario B")
        procesar_escenario(check_esc_c, c_pg_anos, c_anos_aum, c_pct_aum, "Escenario C")

        # --- INICIO TAREA 6 (V33.0): RP con RVD ---
        if check_rp_rvd:
            
            # 1. Calcular Factor Temporal de RP (ft_rp)
            (ft_rp, _) = calcular_factores_combinados(
                datos_afiliado, 
                datos_conyuge, datos_hijos,
                None, # No usa VTD
                TABLAS_DE_MORTALIDAD_REALES,
                modo_calculo='RP',
                tasa_plana_rp=tasa_rp_decimal,
                periodo_garantizado_en_anos=0,
                anos_de_aumento=n_anos_diferimiento # N años
            )
            
            # 2. Calcular Factor Diferido de RVI (fd_rvi)
            (_, fd_rvi) = calcular_factores_combinados(
                datos_afiliado, 
                datos_conyuge, datos_hijos,
                VECTOR_VTD, 
                TABLAS_DE_MORTALIDAD_REALES,
                modo_calculo=modo_calculo_rvi_final,
                tasa_plana_rp=tasa_plana_rvi_final,
                periodo_garantizado_en_anos=0, # RVD simple
                anos_de_aumento=n_anos_diferimiento # N años
            )

            # 3. Calcular Factor Híbrido Ajustado por comisión
            denominador_comision = (1 - comision_decimal)
            if denominador_comision == 0:
                st.error("Error: Comisión del 100% no es válida.")
                st.stop()
                
            factor_hibrido_ajustado = ft_rp + (fd_rvi / denominador_comision)
            
            if factor_hibrido_ajustado <= 0:
                st.error("Error: Factor híbrido es cero o negativo.")
                st.stop()

            # 4. Calcular Pensión
            pension_anual_uf = prima_neta_rp / factor_hibrido_ajustado
            pension_mensual_uf = pension_anual_uf / 12.0
            
            # 5. Calcular valores en CLP para ambos períodos
            
            # --- Período RP (Paga 7% salud + Comisión AFP) ---
            comision_pct_afp = AFP_COMMISSIONS.get(input_afp_nombre, 0.0) / 100.0
            comision_uf_afp = pension_mensual_uf * comision_pct_afp
            pension_uf_neta_rp = pension_mensual_uf - comision_uf_afp
            
            bruto_clp_rp, dscto_clp_rp, liq_clp_rp = calcular_descuentos_clp(
                pension_uf_neta_rp, input_valor_uf_clp
            )
            comision_clp_afp = comision_uf_afp * input_valor_uf_clp
            
            # --- Período RVD (Paga SÓLO 7% salud) ---
            bruto_clp_rvd, dscto_clp_rvd, liq_clp_rvd = calcular_descuentos_clp(
                pension_mensual_uf, input_valor_uf_clp
            )

            # 6. Añadir a las filas del reporte
            rvd_rows.append({
                "Modalidad": f"RP-RVD (Meses 1 a {n_anos_diferimiento * 12})",
                "Pensión (UF)": pension_uf_neta_rp, # Neta de AFP
                "Pensión M. Bruto": bruto_clp_rp,
                "Comisión AFP": comision_clp_afp, 
                "Dscto. 7% Salud": dscto_clp_rp,
                "Pensión Liquida": liq_clp_rp
            })
            
            rvd_rows.append({
                "Modalidad": f" - (P. RVD desde mes {n_anos_diferimiento * 12 + 1})",
                "Pensión (UF)": pension_mensual_uf, # Bruta (sin AFP)
                "Pensión M. Bruto": bruto_clp_rvd,
                "Comisión AFP": 0.0, # No hay comisión AFP
                "Dscto. 7% Salud": dscto_clp_rvd,
                "Pensión Liquida": liq_clp_rvd
            })
        # --- FIN TAREA 6 (V33.0) ---

    # --- FIN REFACTOR V32.0 ---
    
    # --- Guardar los datos para el constructor de PDF (MODIFICADO V34.0) ---
    report_data = {
        "input_afiliado_nombre": input_afiliado_nombre,
        "input_valor_uf_clp": input_valor_uf_clp,
        "saldo_uf": saldo_uf,
        "afiliado_edad_calculada": afiliado_edad_calculada,
        "afiliado_tipo_pension": afiliado_tipo_pension, # V32
        "es_sobrevivencia": (afiliado_tipo_pension == 'Sobrevivencia'), # V32
        "incluye_conyuge": incluye_conyuge,
        "datos_conyuge": datos_conyuge, 
        "datos_hijos": datos_hijos,
        "afp_details_str": afp_details_str,
        "comision_header_str": comision_header_str, 
        "rp_rows": rp_rows,
        "rvi_simple_rows": rvi_simple_rows,
        "rvat_rows": rvat_rows,
        "rvd_rows": rvd_rows, # V33
        "vtd_details": vtd_details_str, 
        "metodo_rvi_desc": metodo_rvi_desc, # V30/V34
        "check_incluye_pgu": check_incluye_pgu,
        "check_incluye_bono": check_incluye_bono,
        "input_valor_pgu_clp": input_valor_pgu_clp,
        "input_bonificacion_uf": input_bonificacion_uf,
        "check_incluye_comision": check_incluye_comision, # P3
        "input_comision_pct": input_comision_pct, # P3
        "prima_neta_rvi": prima_neta_rvi # P3
    }
    
    pdf_bytes = create_native_pdf_report(report_data)
    
    st.session_state.report_data = report_data
    st.session_state.pdf_bytes = pdf_bytes
    st.session_state.report_generated = True
    
    st.success("Informe generado. El reporte se muestra abajo. Haz clic en 'Descargar PDF' para guardarlo.")

# --- 5. MOSTRAR LOS RESULTADOS EN LA PÁGINA (MODIFICADO V34.0) ---

if st.session_state.report_generated:
    
    data = st.session_state.report_data
    
    st.markdown('<div id="reporte-en-pantalla">', unsafe_allow_html=True)
    
    st.markdown("---")
    st.title("ESTUDIO PRELIMINAR DE PENSIÓN", anchor=False) # H1
    st.header(f"SR. {data['input_afiliado_nombre'].upper()}", anchor=False) # H2
    
    st.markdown(f"**Valor UF Utilizado:** `${data['input_valor_uf_clp']:,.0f}`".replace(",", "."))
    
    # --- INICIO V32.0 ---
    if not data.get('es_sobrevivencia', False):
        st.markdown(f"**Edad Afiliado:** `{data['afiliado_edad_calculada']} años ({data['afiliado_tipo_pension']})`")
    # --- FIN V32.0 ---
    
    if data['incluye_conyuge']:
        tipo_conyuge = "Inválido" if data['datos_conyuge']['es_invalido'] else ""
        st.markdown(f"**Beneficiario Conyuge:** `{data['datos_conyuge']['edad']} años {tipo_conyuge}`") 
    
    st.markdown(f"**Saldo Acumulado (Bruto):** `{data['saldo_uf']:,.0f} UF`".replace(",", ".")) 
    
    if data['check_incluye_comision']:
        st.caption(f":grey[Se descuenta {data['input_comision_pct']:.2f}% de comisión. Prima Neta RVI: {data['prima_neta_rvi']:,.0f} UF]".replace(",", "."))

    st.markdown("---")

    # --- TABLA 1: RETIRO PROGRAMADO ---
    if data['rp_rows']:
        st.subheader("1. Retiro Programado", anchor=False) # H3
        
        if data.get('afp_details_str', ''):
            st.caption(data['afp_details_str'])
            
        df_rp = pd.DataFrame(data['rp_rows'])
        
        com_header = data.get('comision_header_str', 'Comisión AFP')
        df_rp = df_rp.rename(columns={"Comisión AFP": com_header})
        
        col_order_rp = [
            "Modalidad", "Pensión (UF)", "Pensión M. Bruto",
            com_header, "Dscto. 7% Salud", "Pensión Liquida"
        ]
        
        st.dataframe(
            df_rp[col_order_rp].style
                .format("{:,.2f} UF", subset=["Pensión (UF)"])
                .format("${:,.0f}", subset=["Pensión M. Bruto", "Pensión Liquida"])
                .format("-{:,.0f}", subset=[com_header, "Dscto. 7% Salud"]),
            hide_index=True, use_container_width=True
        )

    # --- TABLA 2: RENTAS VITALICIAS INMEDIATAS (MODIFICADO V34.0) ---
    if data['rvi_simple_rows']:
        
        # --- INICIO CAMBIO V32.0 ---
        title_rvi_screen = "2. Renta Vitalicia Inmediata (Simple y Garantizada)"
        if data.get('es_sobrevivencia', False):
             title_rvi_screen = "2. Pensiones de Sobrevivencia"
        # --- FIN CAMBIO V32.0 ---
             
        st.subheader(title_rvi_screen, anchor=False) # H3
        st.caption(f":grey[{data['metodo_rvi_desc']}]") # V30/V34
        
        df_simple = pd.DataFrame(data['rvi_simple_rows'])
        
        # --- INICIO CAMBIO V34.0 ---
        # Asegurar el orden de las columnas
        cols_order_rvi = [
            "Modalidad", "Tasa (%)", "Pensión (UF)", 
            "Pensión M. Bruto", "Dscto. 7% Salud", "Pensión Liquida"
        ]
        # Filtrar columnas que existen en el df (ej. si hay filas de PGU/Bono)
        cols_to_show_rvi = [col for col in cols_order_rvi if col in df_simple.columns]
        
        st.dataframe(
            df_simple[cols_to_show_rvi].style
                .format("{:,.2f}%", subset=["Tasa (%)"], na_rep="")
                .format("{:,.2f} UF", subset=["Pensión (UF)"], na_rep="")
                .format("${:,.0f}", subset=["Pensión M. Bruto", "Pensión Liquida"], na_rep="")
                .format("-{:,.0f}", subset=["Dscto. 7% Salud"], na_rep=""),
            hide_index=True, use_container_width=True
        )
        # --- FIN CAMBIO V34.0 ---

    # --- TABLA 3: RENTAS VITALICIAS CON AUMENTO TEMPORAL ---
    if data['rvat_rows']:
        st.subheader("3. Renta Vitalicia con Aumento Temporal", anchor=False) # H3
        df_complex = pd.DataFrame(data['rvat_rows'])
        
        cols_to_show = [col for col in df_complex.columns if not col.startswith('is_')]
        
        st.dataframe(
            df_complex[cols_to_show].style
                .format("{:,.2f} UF", subset=["Pensión (UF)"], na_rep="")
                .format("${:,.0f}", subset=["Pensión M. Bruto", "Pensión Liquida"], na_rep="")
                .format("-{:,.0f}", subset=["Dscto. 7% Salud"], na_rep=""),
            hide_index=True, use_container_width=True
        )
        
    # --- TABLA 4: RP con RVD (NUEVO V33.0) ---
    if data['rvd_rows']:
        st.subheader("4. Retiro Programado con Renta Vitalicia Diferida", anchor=False) # H3
        st.caption(f":grey[{data['metodo_rvi_desc']}]") # Subtítulo
        
        df_rvd = pd.DataFrame(data['rvd_rows'])
        
        com_header = data.get('comision_header_str', 'Comisión AFP')
        df_rvd = df_rvd.rename(columns={"Comisión AFP": com_header})
        
        cols_to_show_rvd = [
            "Modalidad", "Pensión (UF)", "Pensión M. Bruto",
            com_header, "Dscto. 7% Salud", "Pensión Liquida"
        ]
        
        st.dataframe(
            df_rvd[cols_to_show_rvd].style
                .format("{:,.2f} UF", subset=["Pensión (UF)"], na_rep="")
                .format("${:,.0f}", subset=["Pensión M. Bruto", "Pensión Liquida"], na_rep="")
                .format("-{:,.0f}", subset=[com_header, "Dscto. 7% Salud"], na_rep=""),
            hide_index=True, use_container_width=True
        )

    # --- Pie de Página del Reporte ---
    st.markdown("---")
    st.caption("NOTA: VALORES ESTIMATIVOS NO CONSTITUYEN UNA OFERTA FORMAL DE PENSIÓN.")
    st.caption("LA PGU SE SOLICITA A LOS 65 AÑOS, REQUISITO TENER REGISTRO SOCIAL DE HOGARES Y NO PERTENECER AL 90% DE MAYORES INGRESOS.")
    st.caption("BONIFICACIÓN POR AÑO COTIZADO SE COMIENZA A PAGAR A LOS 9 MESES DE PUBLICADA LA LEY. LA BONIFICACIÓN SON 0.1 UF POR AÑO COTIZADO PARTIENDO DE LOS 20 AÑOS, MAXIMO 2,5 UF.")
    
    st.markdown('</div>', unsafe_allow_html=True)

    # --- BOTÓN DE DESCARGA ---
    st.download_button(
        label="🖨️ Descargar Informe (PDF)",
        data=st.session_state.pdf_bytes,
        file_name=f"estudio_pension_{input_afiliado_nombre.replace(' ', '_')}.pdf",
        mime="application/pdf",
        key="download_button"
    )