import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# ==========================================
# CONFIGURACIÓN
# ==========================================
st.set_page_config(page_title="Gestor Rutas Ambulancias", layout="wide")

# Tiempos Estimados (en minutos)
T_SALIDA_BASE = 15
T_SERVICIO = 10
T_TRASLADO = 15
T_RETORNO = 15
DURACION_VIAJE_ESTANDAR = T_SALIDA_BASE + T_SERVICIO + T_TRASLADO + T_SERVICIO + T_RETORNO # Total ~65 min

# Capacidades
FLOTA_CONFIG = {
    'A': {'qty': 5,  'camilla': 0, 'silla': 2, 'asiento': 4},
    'B': {'qty': 18, 'camilla': 1, 'silla': 1, 'asiento': 5}
}

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def minutes_to_time(base_time, minutes_added):
    """Convierte minutos agregados a una hora HH:MM"""
    new_time = base_time + timedelta(minutes=int(minutes_added))
    return new_time.strftime("%H:%M")

def get_patient_requirements(tipo_str):
    """Devuelve qué consume el paciente: (camilla, silla, asiento)"""
    t = str(tipo_str).lower().strip()
    if 'uvi' in t or 'camilla' in t:
        return 1, 0, 0 # 1 camilla
    elif 'silla' in t:
        return 0, 1, 0 # 1 silla
    else:
        return 0, 0, 1 # 1 asiento

# ==========================================
# MOTOR DE ASIGNACIÓN (LÓGICA SIMPLE)
# ==========================================
def planificar_rutas(df, hora_inicio_str):
    """
    Algoritmo:
    1. Crea la flota de vehículos.
    2. Ordena pacientes (prioridad Camilla/UVI).
    3. Itera por cada vehículo y trata de llenarlo con viajes consecutivos hasta fin de jornada.
    """
    
    # 1. Preparar Flota
    vehiculos = []
    # Crear Vehículos Tipo A
    for i in range(FLOTA_CONFIG['A']['qty']):
        vehiculos.append({
            'id': f"A-{i+1}", 
            'tipo': 'A', 
            'caps': FLOTA_CONFIG['A'].copy(), 
            'minutos_acumulados': 0
        })
    # Crear Vehículos Tipo B
    for i in range(FLOTA_CONFIG['B']['qty']):
        vehiculos.append({
            'id': f"B-{i+1}", 
            'tipo': 'B', 
            'caps': FLOTA_CONFIG['B'].copy(), 
            'minutos_acumulados': 0
        })

    # 2. Preparar Pacientes
    # Prioridad: UVI/Camilla > Silla > Sentado (para asegurar que los B se usen bien)
    df['assigned'] = False
    
    # Convertir hora inicio
    start_dt = datetime.strptime(hora_inicio_str, "%H:%M")
    
    rutas_generadas = []
    
    # Jornada en minutos (8 horas = 480 min)
    JORNADA_MAX = 480 

    # 3. Asignación
    for veh in vehiculos:
        # Mientras el vehículo tenga tiempo para hacer al menos un viaje más
        while veh['minutos_acumulados'] + DURACION_VIAJE_ESTANDAR <= JORNADA_MAX:
            
            # --- NUEVO VIAJE (BATCH) ---
            viaje_pacientes = []
            
            # Capacidad actual para este viaje
            cap_camilla = veh['caps']['camilla']
            cap_silla = veh['caps']['silla']
            cap_asiento = veh['caps']['asiento']
            
            hay_espacio = True
            
            # Buscar pacientes no asignados que quepan en este viaje
            # Iteramos sobre el DF global buscando candidatos
            for idx, row in df.iterrows():
                if row['assigned']:
                    continue
                
                req_c, req_s, req_a = get_patient_requirements(row['Tipo'])
                
                # Verificar si cabe
                if cap_camilla >= req_c and cap_silla >= req_s and cap_asiento >= req_a:
                    # ASIGNAR
                    df.at[idx, 'assigned'] = True
                    cap_camilla -= req_c
                    cap_silla -= req_s
                    cap_asiento -= req_a
                    
                    viaje_pacientes.append(row)
                    
                    # Si ya no cabe nada más (optimización básica), dejar de buscar
                    if cap_camilla == 0 and cap_silla == 0 and cap_asiento == 0:
                        break
            
            # Si asignamos al menos un paciente en este viaje, registramos el viaje
            if len(viaje_pacientes) > 0:
                hora_salida_viaje = minutes_to_time(start_dt, veh['minutos_acumulados'])
                hora_fin_viaje = minutes_to_time(start_dt, veh['minutos_acumulados'] + DURACION_VIAJE_ESTANDAR)
                
                for p in viaje_pacientes:
                    rutas_generadas.append({
                        'Vehículo': veh['id'],
                        'Tipo Veh': veh['tipo'],
                        'Salida Base': hora_salida_viaje,
                        'Paciente': p['Paciente'],
                        'Tipo Paciente': p['Tipo'],
                        'Recogida': p['Recogida'],
                        'Destino': p['Destino'],
                        'Fin Viaje': hora_fin_viaje,
                        'Grupo Viaje': f"{veh['id']}-{int(veh['minutos_acumulados'])}"
                    })
                
                # Consumir tiempo del vehículo
                veh['minutos_acumulados'] += DURACION_VIAJE_ESTANDAR
            else:
                # Si no encontramos ningún paciente que quepa, pasamos al siguiente vehículo
                break
                
    return pd.DataFrame(rutas_generadas), df[df['assigned']==False]

# ==========================================
# UI PRINCIPAL
# ==========================================
st.title("🚑 Generador de Hojas de Ruta")
st.markdown("Planificación automática de jornada de 8 horas con tiempos estimados.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configuración Jornada")
    hora_inicio = st.time_input("Hora Inicio", value=datetime.strptime("08:00", "%H:%M").time())
    st.info("**Tiempos Estimados por Viaje:**\n\n- Salida Base: 15 min\n- Recogida (+10min): 25 min\n- Traslado: 15 min\n- Entrega (+10min): 25 min\n- Retorno: 15 min\n\n**Total Bloque: ~65 min**")

# --- CARGA ---
uploaded_file = st.file_uploader("Cargar Excel Pacientes", type=['xlsx'])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    
    # Validación básica
    req_cols = ['Paciente', 'Recogida', 'Destino', 'Tipo']
    if not all(c in df.columns for c in req_cols):
        st.error(f"Faltan columnas. Requeridas: {req_cols}")
    else:
        st.success(f"Cargados {len(df)} pacientes.")
        
        if st.button("📅 Generar Hojas de Ruta", type="primary"):
            
            # EJECUTAR LÓGICA
            hora_str = hora_inicio.strftime("%H:%M")
            df_rutas, df_pendientes = planificar_rutas(df.copy(), hora_str)
            
            # --- RESULTADOS ---
            
            # 1. Métricas
            total_asig = len(df) - len(df_pendientes)
            col1, col2, col3 = st.columns(3)
            col1.metric("Pacientes Asignados", f"{total_asig}/{len(df)}")
            col2.metric("Vehículos Usados", df_rutas['Vehículo'].nunique() if not df_rutas.empty else 0)
            col3.metric("Viajes Realizados", df_rutas['Grupo Viaje'].nunique() if not df_rutas.empty else 0)
            
            if not df_pendientes.empty:
                st.warning(f"⚠️ Atención: {len(df_pendientes)} pacientes no cupieron en la jornada de 8h con la flota actual.")
                with st.expander("Ver pacientes no asignados"):
                    st.dataframe(df_pendientes)

            if not df_rutas.empty:
                st.divider()
                st.subheader("📋 Hojas de Ruta por Vehículo")
                
                # Visualización agrupada
                vehiculos_usados = sorted(df_rutas['Vehículo'].unique())
                
                # Select box para filtrar en pantalla
                v_select = st.selectbox("Seleccionar Vehículo para visualizar:", vehiculos_usados)
                
                # Mostrar tabla filtrada
                v_df = df_rutas[df_rutas['Vehículo'] == v_select]
                st.table(v_df[['Salida Base', 'Paciente', 'Tipo Paciente', 'Recogida', 'Destino', 'Fin Viaje']])
                
                # --- EXPORTAR EXCEL ---
                st.divider()
                
                # Crear Excel en memoria
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Hoja General
                    df_rutas.to_excel(writer, index=False, sheet_name='Ruta_Completa')
                    
                    # Hojas por Vehículo
                    for v in vehiculos_usados:
                        sub_df = df_rutas[df_rutas['Vehículo'] == v]
                        sub_df.to_excel(writer, index=False, sheet_name=v)
                        
                processed_data = output.getvalue()
                
                st.download_button(
                    label="📥 Descargar Excel Completo (Hojas por Vehículo)",
                    data=processed_data,
                    file_name=f"hojas_ruta_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("No se pudieron generar rutas. Revisa los datos de entrada.")

else:
    # Plantilla
    st.info("Sube un archivo Excel con columnas: Paciente, Recogida, Destino, Tipo")
    ejemplo = pd.DataFrame([
        ['Juan Perez', 'Calle A', 'Hospital', 'Silla'],
        ['Ana Gomez', 'Calle B', 'Hospital', 'Camilla'],
        ['Luis R', 'Calle C', 'Hospital', 'Sentado']
    ], columns=['Paciente', 'Recogida', 'Destino', 'Tipo'])
    st.download_button("Descargar Plantilla", ejemplo.to_excel(index=False).read(), "plantilla.xlsx")
