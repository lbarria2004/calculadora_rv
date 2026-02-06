from fpdf import FPDF

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
