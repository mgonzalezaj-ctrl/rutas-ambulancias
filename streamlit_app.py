import streamlit as st
import pandas as pd
import math

# ==========================================
# CONFIGURACIÓN BÁSICA
# ==========================================
st.set_page_config(page_title="Calculadora Flota Simple", layout="centered")

st.title("🚑 Calculadora de Flota de Ambulancias")
st.markdown("Versión simplificada: Cálculo de capacidad por tipo de paciente.")

# --- DATOS DE FLOTA FIJA ---
FLOTA_A_TOTAL = 5   # Cap: 2 Sillas + 4 Sentados
FLOTA_B_TOTAL = 18  # Cap: 1 Camilla + 1 Silla + 5 Sentados

# ==========================================
# 1. CARGA DE DATOS
# ==========================================
st.subheader("1. Cargar Datos")

uploaded_file = st.file_uploader("Sube tu Excel (.xlsx)", type=['xlsx'])

# Botón para generar plantilla si no tienen archivo
if not uploaded_file:
    data_ejemplo = {
        'Paciente': ['Juan', 'Ana', 'Luis', 'Pedro', 'Maria', 'Jose'],
        'Tipo': ['Silla', 'Camilla', 'Sentado', 'UVI', 'Silla', 'Sentado'],
        'Hora': ['09:00', '09:00', '09:00', '10:00', '10:00', '11:00'],
        'Recogida': ['Dir A', 'Dir B', 'Dir C', 'Dir D', 'Dir E', 'Dir F'],
        'Destino': ['Hosp', 'Hosp', 'Hosp', 'Hosp', 'Hosp', 'Hosp']
    }
    df_ejemplo = pd.DataFrame(data_ejemplo)
    st.info("Sube un archivo. ¿No tienes uno? Descarga esta plantilla:")
    st.download_button(
        label="Descargar Plantilla Ejemplo",
        data=df_ejemplo.to_excel(index=False).read(), # Requiere openpyxl instalado
        file_name="plantilla_pacientes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    # Leer archivo
    try:
        df = pd.read_excel(uploaded_file)
        
        # Normalizar columna Tipo (minúsculas y sin espacios)
        if 'Tipo' in df.columns:
            df['Tipo'] = df['Tipo'].astype(str).str.lower().str.strip()
        else:
            st.error("El Excel debe tener una columna llamada 'Tipo'")
            st.stop()

        # ==========================================
        # 2. MOSTRAR TABLA Y CONTEOS
        # ==========================================
        st.subheader("2. Resumen de Pacientes")
        
        # Contar tipos
        n_uvi = len(df[df['Tipo'] == 'uvi'])
        n_camilla = len(df[df['Tipo'] == 'camilla'])
        n_silla = len(df[df['Tipo'] == 'silla'])
        n_sentado = len(df[df['Tipo'] == 'sentado'])
        
        # Casos raros (errores de escritura) se cuentan como sentados por defecto
        conocidos = n_uvi + n_camilla + n_silla + n_sentado
        n_otros = len(df) - conocidos
        if n_otros > 0:
            n_sentado += n_otros
            st.warning(f"Se detectaron {n_otros} tipos desconocidos. Se contarán como 'Sentado'.")

        # Mostrar métricas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("UVI", n_uvi)
        col2.metric("Camilla", n_camilla)
        col3.metric("Silla", n_silla)
        col4.metric("Sentado", n_sentado)
        
        st.dataframe(df.head())

        # ==========================================
        # 3. LÓGICA DE ASIGNACIÓN (CÁLCULO)
        # ==========================================
        st.divider()
        if st.button("🔢 Calcular Vehículos Necesarios", type="primary"):
            
            # --- ALGORITMO DE ASIGNACIÓN PASO A PASO ---
            
            # Inicializamos contadores de uso
            uso_a = 0
            uso_b = 0
            
            # PASO 1: CAMILLAS y UVI (Prioridad Absoluta)
            # Solo caben en Tipo B (1 por vehículo)
            total_camillas = n_uvi + n_camilla
            uso_b += total_camillas
            
            # Capacidad residual de los vehículos B ya usados:
            # Cada B tiene hueco para 1 Silla y 5 Sentados extra
            cap_silla_disponible = uso_b * 1
            cap_sentado_disponible = uso_b * 5
            
            # PASO 2: SILLAS
            # Restamos las sillas que caben en los B que ya hemos sacado
            sillas_restantes = max(0, n_silla - cap_silla_disponible)
            
            # Si quedan sillas, usamos Tipo A (caben 2 por vehículo)
            while sillas_restantes > 0:
                if uso_a < FLOTA_A_TOTAL:
                    uso_a += 1
                    sillas_restantes -= 2
                    # Este A nuevo aporta 4 asientos
                    cap_sentado_disponible += 4 
                else:
                    # Si se acaban los A, usamos B (cabe 1 por vehículo)
                    uso_b += 1
                    sillas_restantes -= 1
                    cap_sentado_disponible += 5 # Este B nuevo aporta 5 asientos
            
            # PASO 3: SENTADOS
            # Restamos los sentados que caben en los huecos libres de los vehículos ya asignados
            sentados_restantes = max(0, n_sentado - cap_sentado_disponible)
            
            # Si quedan sentados, llenamos flotas
            while sentados_restantes > 0:
                # Priorizamos llenar A si quedan (son más pequeños/baratos teóricamente)
                if uso_a < FLOTA_A_TOTAL:
                    uso_a += 1
                    sentados_restantes -= 4 # A tiene 4 asientos + 2 sillas (usamos todo como asientos si es necesario)
                else:
                    uso_b += 1
                    sentados_restantes -= 5 # B tiene 5 asientos
            
            # ==========================================
            # 4. RESULTADOS
            # ==========================================
            st.subheader("3. Resultado de la Asignación")
            
            # Comprobar si nos pasamos de la flota real
            alert_a = "✅ OK" if uso_a <= FLOTA_A_TOTAL else f"❌ FALTAN {uso_a - FLOTA_A_TOTAL}"
            alert_b = "✅ OK" if uso_b <= FLOTA_B_TOTAL else f"❌ FALTAN {uso_b - FLOTA_B_TOTAL}"
            
            c_res1, c_res2 = st.columns(2)
            
            with c_res1:
                st.info(f"**Vehículos Tipo A**\n\nNecesarios: **{uso_a}** / {FLOTA_A_TOTAL}\n\nEstado: {alert_a}")
                
            with c_res2:
                st.info(f"**Vehículos Tipo B**\n\nNecesarios: **{uso_b}** / {FLOTA_B_TOTAL}\n\nEstado: {alert_b}")

            # Resumen final
            if uso_a <= FLOTA_A_TOTAL and uso_b <= FLOTA_B_TOTAL:
                st.success(f"La flota es suficiente para transportar a los {len(df)} pacientes.")
            else:
                st.error("⚠️ La flota NO es suficiente. Necesitas más vehículos o hacer varios viajes.")

    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
