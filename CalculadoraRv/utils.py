import pandas as pd
import streamlit as st
from datetime import date

# --- 0. FUNCIÓN AYUDANTE PARA CALCULAR EDAD ---
def calculate_age(born):
    """
    Calcula la edad exacta (años cumplidos) desde la fecha de nacimiento.
    """
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age

# --- 1. CARGA DE DATOS (EXCEL) ---

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
        
        st.error("VERIFICA que los nombres en el script coincidan 100% con lo que se muestra en la lista de arriba.")
        return None
    # --- FIN BLOQUE DEBUG V24.5 ---
        
    except FileNotFoundError:
        st.error(f"Error: No se encontró el archivo '{archivo_etti_cmf}'.")
        return None
    except Exception as e:
        st.error(f"Error al procesar el archivo VTD: {e}")
        return None

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

def calcular_descuentos_clp(pension_uf, valor_uf):
    """
    Calcula los montos en pesos, el descuento de salud y el líquido.
    """
    pension_bruta_clp = pension_uf * valor_uf
    descuento_salud_clp = pension_bruta_clp * 0.07 # 7% de descuento
    pension_liquida_clp = pension_bruta_clp - descuento_salud_clp
    return pension_bruta_clp, descuento_salud_clp, pension_liquida_clp
