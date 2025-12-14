import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta
import io

# ==========================================
# CONFIGURACIÓN
# ==========================================
st.set_page_config(page_title="Gestor Ambulancias Simple", layout="wide")
st.title("🚑 Gestor de Flota - Versión Estable")

# Configuración fija
DURACION_SERVICIO = 60  # Minutos fijos por servicio
UBICACIONES = [
    "Hospital Santa Bárbara", "Los Royales", "Centro Salud La Milagrosa", 
    "Plaza Mayor", "Estación Autobuses", "San Andrés", "Golmayo", 
    "Polígono Las Casas", "Almazán", "Garray"
]
TIPOS = ["Sentado"] * 50 + ["Silla"] * 30 + ["Camilla"] * 15 + ["UVI"] * 5

# ==========================================
# 1. GENERADOR DE DATOS
# ==========================================
def generar_datos():
    data = []
    start_time = datetime.strptime("08:00", "%H:%M")
    
    for i in range(1, 101):
        # Hora aleatoria entre 08:00 y 16:00
        min_offset = random.randint(0, 480)
        hora_cita = start_time + timedelta(minutes=min_offset)
        
        row = {
            "ID_Servicio": i,
            "Hora_Cita": hora_cita.strftime("%H:%M"),
            "Paciente": f"Paciente {i}",
            "Recogida": random.choice(UBICACIONES),
            "Destino": random.choice(UBICACIONES),
            "Tipo": random.choice(TIPOS)
        }
        # Evitar origen == destino
        while row['Recogida'] == row['Destino']:
            row['Destino'] = random.choice(UBICACIONES)
            
        data.append(row)
    
    df = pd.DataFrame(data)
    return df.sort_values("Hora_Cita")

# ==========================================
# 2. LOGICA DE FLOTA Y ASIGNACIÓN
# ==========================================
def crear_flota():
    flota = []
    # 5 Vehículos Tipo A (A-001 a A-005) - NO aptos para Camilla/UVI
    for i in range(1, 6):
        flota.append({
            "id": f"A-{i:03d}", 
            "tipo": "A", 
            "disponible_desde": datetime.strptime("08:00", "%H:%M")
        })
    
    # 18 Vehículos Tipo B (B-001 a B-018) - Aptos para TODO
    for i in range(1, 19):
        flota.append({
            "id": f"B-{i:03d}", 
            "tipo": "B", 
            "disponible_desde": datetime.strptime("08:00", "%H:%M")
        })
    return flota

def puede_llevar(vehiculo_tipo, paciente_tipo):
    # Tipo A solo lleva Sentado o Silla
    if vehiculo_tipo == "A":
        if paciente_tipo in ["Camilla", "UVI"]:
            return False
    return True

# ==========================================
# 3. INTERFAZ
# ==========================================

# Paso 1: Generar
if st.button("🔄 Generar 100 Servicios"):
    df = generar_datos()
    st.session_state['df_servicios'] = df
    st.success("✅ 100 Servicios generados. Pulsa 'Asignar' para procesar.")

# Mostrar datos si existen
if 'df_servicios' in st.session_state:
    st.dataframe(st.session_state['df_servicios'].head(), use_container_width=True)
    
    # Paso 2: Asignar
    if st.button("🚀 Asignar Vehículos (Algoritmo Simple)"):
        
        df_proc = st.session_state['df_servicios'].copy()
        flota = crear_flota()
        resultados = []
        
        # Base de fecha para comparaciones
        hoy = datetime.today().date()
        
        for index, row in df_proc.iterrows():
            # Convertir hora string a datetime completo para comparar
            hora_cita_str = row['Hora_Cita']
            hora_cita_dt = datetime.strptime(hora_cita_str, "%H:%M")
            
            # Buscar candidatos (vehículos que soporten el tipo de paciente)
            candidatos = [v for v in flota if puede_llevar(v['tipo'], row['Tipo'])]
            
            # ORDENAR candidatos: Primero el que se libere antes
            # Esto evita "saltos" y rellena huecos
            candidatos.sort(key=lambda x: x['disponible_desde'])
            
            asignado = None
            
            # Seleccionar el mejor candidato (el primero de la lista ordenada)
            if candidatos:
                mejor_vehiculo = candidatos[0]
                
                # Calcular cuándo empieza realmente el servicio
                # Es el máximo entre: La hora de la cita Y cuando se libra el vehículo
                inicio_real = max(hora_cita_dt, mejor_vehiculo['disponible_desde'])
                fin_real = inicio_real + timedelta(minutes=DURACION_SERVICIO)
                
                # Actualizar vehículo
                mejor_vehiculo['disponible_desde'] = fin_real
                
                asignado = mejor_vehiculo['id']
                hora_inicio_real_str = inicio_real.strftime("%H:%M")
                hora_fin_str = fin_real.strftime("%H:%M")
            else:
                asignado = "SIN FLOTA"
                hora_inicio_real_str = "-"
                hora_fin_str = "-"

            # Guardar resultado
            resultados.append({
                "Vehículo": asignado,
                "Hora Cita": row['Hora_Cita'],
                "Inicio Real": hora_inicio_real_str,
                "Fin Servicio": hora_fin_str,
                "Paciente": row['Paciente'],
                "Recogida": row['Recogida'],
                "Destino": row['Destino'],
                "Tipo": row['Tipo']
            })
            
        # Crear DataFrame Final
        df_final = pd.DataFrame(resultados)
        st.session_state['df_resultado'] = df_final
        st.success("Cálculo completado.")

# Paso 3: Mostrar y Descargar
if 'df_resultado' in st.session_state:
    st.divider()
    st.subheader("📋 Resultados de Asignación")
    
    df_res = st.session_state['df_resultado']
    st.dataframe(df_res, use_container_width=True)
    
    # Exportar Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_res.to_excel(writer, index=False, sheet_name='Hoja_Ruta')
        
    st.download_button(
        label="📥 Descargar Excel",
        data=buffer.getvalue(),
        file_name="rutas_ambulancias.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
