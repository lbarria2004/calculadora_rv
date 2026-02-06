import streamlit as st
from utils import obtener_prob_supervivencia

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
