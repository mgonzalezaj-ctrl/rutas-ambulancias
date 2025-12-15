# ==========================================
# GESTOR INTELIGENTE DE FLOTA DE AMBULANCIAS PRO
# Versión Profesional con Gestión de Vehículos Personalizada
# ==========================================

import streamlit as st
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta, time
import io
from collections import defaultdict
import math

# ==========================================
# CONFIGURACIÓN
# ==========================================

st.set_page_config(
    page_title="🏆 Gestor Pro de Flota",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏆 Gestor Inteligente de Flota de Ambulancias PRO")
st.markdown("""### Sistema Avanzado con Gestión Personalizada de Vehículos
**Características PRO:**
- 🚗 Gestión personalizada de vehículos y conductores
- ⏰ Cálculo automático de hora de entrada por conductor
- 📊 Jornadas flexibles (hasta 10h con optimización)
- 📋 Hojas Excel individuales por conductor con jornada completa
- 🎯 Balance inteligente de carga
- 📈 KPIs profesionales en tiempo real
---
""")

# Configuración global
DURACION_SERVICIO = 60  # Minutos
JORNADA_BASE = 8 * 60  # 8 horas
JORNADA_MAX_FLEXIBLE = 10 * 60  # 10 horas máximo
MARGEN_TIEMPO = 30  # Margen antes/después cita

UBICACIONES = [
    "Hospital Santa Bárbara", "Los Royales", "Centro Salud La Milagrosa",
    "Plaza Mayor", "Estación Autobuses", "San Andrés", "Golmayo",
    "Polígono Las Casas", "Almazán", "Garray"
]

TIPOS = ["Sentado"] * 50 + ["Silla"] * 30 + ["Camilla"] * 15 + ["UVI"] * 5

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def calcular_distancia_simple(loc1, loc2):
    if loc1 == loc2:
        return 0
    ubicaciones_dict = {loc: i for i, loc in enumerate(UBICACIONES)}
    idx1 = ubicaciones_dict.get(loc1, 0)
    idx2 = ubicaciones_dict.get(loc2, 0)
    return abs(idx1 - idx2) * 8 + random.randint(2, 10)

def clustering_geografico(df_servicios, n_clusters=None):
    coords = {}
    for i, loc in enumerate(UBICACIONES):
        angle = (i / len(UBICACIONES)) * 2 * math.pi
        coords[loc] = (math.cos(angle) * 100, math.sin(angle) * 100)
    
    df_servicios['coord_x'] = df_servicios['Recogida'].map(lambda x: coords.get(x, (0,0))[0])
    df_servicios['coord_y'] = df_servicios['Recogida'].map(lambda x: coords.get(x, (0,0))[1])
    df_servicios['zona'] = df_servicios['Recogida'].map(
        lambda x: UBICACIONES.index(x) % (n_clusters if n_clusters else 3)
    )
    return df_servicios

def puede_llevar(vehiculo_tipo, paciente_tipo):
    if vehiculo_tipo == "A":
        return paciente_tipo in ["Sentado", "Silla"]
    return True

def calcular_hora_entrada(servicios_asignados):
    if not servicios_asignados:
        return "08:00"
    primer_servicio = min(servicios_asignados, key=lambda x: datetime.strptime(x['Hora Cita'], "%H:%M"))
    hora_cita = datetime.strptime(primer_servicio['Hora Cita'], "%H:%M")
    tiempo_prep = primer_servicio.get('Tiempo Viaje', 15) + 15
    hora_entrada = hora_cita - timedelta(minutes=tiempo_prep)
    return hora_entrada.strftime("%H:%M")

# ==========================================
# GESTIÓN DE FLOTA PERSONALIZADA
# ==========================================

if 'vehiculos_personalizados' not in st.session_state:
    st.session_state['vehiculos_personalizados'] = []

st.sidebar.header("🚗 Gestión de Flota Personalizada")

with st.sidebar.expander("➕ Añadir Vehículo", expanded=False):
    with st.form("form_vehiculo"):
        col1, col2 = st.columns(2)
        with col1:
            nuevo_id = st.text_input("ID Vehículo", placeholder="Ej: A-001")
            nuevo_tipo = st.selectbox("Tipo", ["A", "B"])
        with col2:
            nuevo_conductor = st.text_input("Conductor", placeholder="Nombre")
            nueva_matricula = st.text_input("Matrícula", placeholder="0000BBB")
        
        if st.form_submit_button("✅ Añadir Vehículo"):
            if nuevo_id and nuevo_conductor:
                st.session_state['vehiculos_personalizados'].append({
                    "id": nuevo_id,
                    "tipo": nuevo_tipo,
                    "conductor": nuevo_conductor,
                    "matricula": nueva_matricula,
                    "disponible_desde": datetime.strptime("08:00", "%H:%M"),
                    "servicios_asignados": [],
                    "tiempo_trabajado": 0
                })
                st.success(f"✅ Vehículo {nuevo_id} añadido")
            else:
                st.error("❌ Completa ID y Conductor")

if st.session_state['vehiculos_personalizados']:
    st.sidebar.subheader(f"📋 Flota Actual ({len(st.session_state['vehiculos_personalizados'])} vehículos)")
    for idx, v in enumerate(st.session_state['vehiculos_personalizados']):
        with st.sidebar.expander(f"{v['id']} - {v['conductor']}"):
            st.write(f"**Tipo:** {v['tipo']}")
            st.write(f"**Matrícula:** {v['matricula']}")
            if st.button(f"🗑️ Eliminar", key=f"del_{idx}"):
                st.session_state['vehiculos_personalizados'].pop(idx)
                st.rerun()

# ==========================================
# OPTIMIZACIÓN DE RUTAS
# ==========================================

def optimizar_rutas_vrptw(df_servicios, flota):
    resultados = []
    hoy = datetime.today().date()
    
    df_servicios = df_servicios.sort_values(['zona', 'Hora_Cita'])
    
    for index, row in df_servicios.iterrows():
        hora_cita_str = row['Hora_Cita']
        hora_dt = pd.to_datetime(hora_cita_str, format='mixed', errors='coerce')
        if pd.isna(hora_dt):
            hora_dt = pd.to_datetime(f"2000-01-01 {hora_cita_str}", errors='coerce')
        hora_cita_dt = hora_dt
        
        ventana_inicio = hora_cita_dt - timedelta(minutes=MARGEN_TIEMPO)
        ventana_fin = hora_cita_dt + timedelta(minutes=MARGEN_TIEMPO)
        
        candidatos = [v for v in flota if puede_llevar(v['tipo'], row['Tipo'])]
        candidatos.sort(key=lambda x: (
            x['disponible_desde'],
            x['tiempo_trabajado'],
            -1 if len(x['servicios_asignados']) > 0 and 
                x['servicios_asignados'][-1].get('Zona') == row.get('zona') else 0
        ))
        
        asignado = None
        
        if candidatos:
            mejor_vehiculo = candidatos[0]
            
            if mejor_vehiculo['servicios_asignados']:
                ultima_ubicacion = mejor_vehiculo['servicios_asignados'][-1]['Destino']
                distancia_km = calcular_distancia_simple(ultima_ubicacion, row['Recogida'])
                tiempo_viaje = distancia_km * 2
            else:
                tiempo_viaje = 15
            
            hora_disponible = mejor_vehiculo['disponible_desde'] + timedelta(minutes=tiempo_viaje)
            inicio_real = max(hora_disponible, ventana_inicio)
            
            if inicio_real <= ventana_fin and mejor_vehiculo['tiempo_trabajado'] < JORNADA_MAX_FLEXIBLE:
                fin_real = inicio_real + timedelta(minutes=DURACION_SERVICIO)
                tiempo_espera = max(0, (ventana_inicio - hora_disponible).total_seconds() / 60)
                
                mejor_vehiculo['disponible_desde'] = fin_real
                tiempo_servicio = tiempo_viaje + tiempo_espera + DURACION_SERVICIO
                mejor_vehiculo['tiempo_trabajado'] += tiempo_servicio
                
                servicio_info = {
                    'Vehículo': mejor_vehiculo['id'],
                    'Conductor': mejor_vehiculo.get('conductor', 'N/A'),
                    'Hora Cita': row['Hora_Cita'],
                    'Ventana Inicio': ventana_inicio.strftime("%H:%M"),
                    'Ventana Fin': ventana_fin.strftime("%H:%M"),
                    'Inicio Real': inicio_real.strftime("%H:%M"),
                    'Fin Servicio': fin_real.strftime("%H:%M"),
                    'Tiempo Espera': int(tiempo_espera),
                    'Paciente': row['Paciente'],
                    'Recogida': row['Recogida'],
                    'Destino': row['Destino'],
                    'Tipo': row['Tipo'],
                    'Zona': row.get('zona', 0),
                    'Tiempo Viaje': int(tiempo_viaje),
                    'Horas Trabajadas': round(mejor_vehiculo['tiempo_trabajado'] / 60, 2)
                }
                
                mejor_vehiculo['servicios_asignados'].append(servicio_info)
                resultados.append(servicio_info)
                asignado = mejor_vehiculo['id']
            else:
                resultados.append({
                    'Vehículo': 'SIN ASIGNAR - TIEMPO INSUFICIENTE',
                    'Conductor': 'N/A',
                    'Hora Cita': row['Hora_Cita'],
                    'Paciente': row['Paciente'],
                    'Recogida': row['Recogida'],
                    'Destino': row['Destino'],
                    'Tipo': row['Tipo'],
                    'Zona': row.get('zona', 0)
                })
        else:
            resultados.append({
                'Vehículo': 'SIN FLOTA DISPONIBLE',
                'Conductor': 'N/A',
                'Hora Cita': row['Hora_Cita'],
                'Paciente': row['Paciente'],
                'Recogida': row['Recogida'],
                'Destino': row['Destino'],
                'Tipo': row['Tipo'],
                'Zona': row.get('zona', 0)
            })
    
    return pd.DataFrame(resultados), flota

# ==========================================
# INTERFAZ PRINCIPAL
# ==========================================

st.subheader("📄 Paso 1: Cargar Servicios")
uploaded_file = st.file_uploader("Sube tu archivo Excel con servicios", type=['xlsx', 'xls'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        if 'ID_Servicio' not in df.columns:
            df['ID_Servicio'] = range(1, len(df) + 1)
        st.session_state['df_servicios'] = df
        st.success(f"✅ {len(df)} servicios cargados")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

if 'df_servicios' in st.session_state:
    df = st.session_state['df_servicios']
    st.dataframe(df.head(10), use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Limpiar Servicios"):
            if 'df_servicios' in st.session_state:
                del st.session_state['df_servicios']
            if 'df_resultado' in st.session_state:
                del st.session_state['df_resultado']
            if 'flota' in st.session_state:
                del st.session_state['flota']
            st.rerun()
    
    with col2:
        if st.button("🔄 Resetear Flota/Resultados"):
            if 'df_resultado' in st.session_state:
                del st.session_state['df_resultado']
            if 'flota' in st.session_state:
                del st.session_state['flota']
            st.rerun()
    
    st.subheader("🚀 Paso 2: Optimizar Rutas")
    
    if not st.session_state['vehiculos_personalizados']:
        st.warning("⚠️ No hay vehículos en la flota. Añade vehículos en el panel lateral.")
    else:
        if st.button("🧠 Optimizar con IA (VRPTW + Clustering)"):
            with st.spinner("🔄 Aplicando clustering geográfico..."):
                df = clustering_geografico(df, n_clusters=3)
            
            with st.spinner("⏳ Optimizando rutas VRPTW..."):
                flota = [v.copy() for v in st.session_state['vehiculos_personalizados']]
                for v in flota:
                    v['disponible_desde'] = datetime.strptime("08:00", "%H:%M")
                    v['servicios_asignados'] = []
                    v['tiempo_trabajado'] = 0
                
                df_resultado, flota = optimizar_rutas_vrptw(df, flota)
                st.session_state['df_resultado'] = df_resultado
                st.session_state['flota'] = flota
            
            st.success("✅ ¡Optimización completada!")

# ==========================================
# RESULTADOS Y DASHBOARD
# ==========================================

if 'df_resultado' in st.session_state:
    df_res = st.session_state['df_resultado']
    flota = st.session_state['flota']
    
    st.subheader("📊 Dashboard PRO de Resultados")
    
    # KPIs principales
    col1, col2, col3, col4 = st.columns(4)
    
    vehiculos_usados = len(df_res[df_res['Vehículo'].str.contains('A-|B-', na=False)]['Vehículo'].unique())
    servicios_ok = len(df_res[df_res['Vehículo'].str.contains('A-|B-', na=False)])
    pendientes = len(df_res) - servicios_ok
    eficiencia = round((servicios_ok/len(df_res))*100, 1) if len(df_res) > 0 else 0
    
    col1.metric("🚑 Vehículos Usados", vehiculos_usados)
    col2.metric("✅ Servicios Asignados", servicios_ok)
    col3.metric("❌ Pendientes", pendientes)
    col4.metric("🎯 Eficiencia", f"{eficiencia}%")
    
    # Tabla de vehículos con horas de entrada calculadas
    st.subheader("👥 Resumen por Conductor")
    
    resumen_conductores = []
    for v in flota:
        if v['servicios_asignados']:
            hora_entrada = calcular_hora_entrada(v['servicios_asignados'])
            hora_salida = v['servicios_asignados'][-1]['Fin Servicio']
            total_horas = round(v['tiempo_trabajado'] / 60, 2)
            num_servicios = len(v['servicios_asignados'])
            
            resumen_conductores.append({
                'Vehículo': v['id'],
                'Conductor': v.get('conductor', 'N/A'),
                'Matrícula': v.get('matricula', 'N/A'),
                'Hora Entrada': hora_entrada,
                'Hora Salida': hora_salida,
                'Total Horas': total_horas,
                'Nº Servicios': num_servicios,
                'Estado': '✅ Completo' if total_horas <= 8 else '⚠️ Jornada Extendida'
            })
    
    if resumen_conductores:
        df_conductores = pd.DataFrame(resumen_conductores)
        st.dataframe(df_conductores, use_container_width=True)
    
    # Tabla completa de resultados
    st.subheader("📋 Tabla Detallada de Resultados")
    st.dataframe(df_res, use_container_width=True)
    
    # ==========================================
    # EXPORTACIÓN PROFESIONAL A EXCEL
    # ==========================================
    
    st.subheader("📥 Exportar Excel Profesional")
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Hoja resumen general
        df_res.to_excel(writer, index=False, sheet_name='Resumen General')
        
        # Hoja por cada conductor con jornada completa
        for v in flota:
            if v['servicios_asignados']:
                conductor_nombre = v.get('conductor', v['id']).replace('/', '-')[:30]
                
                # Crear DataFrame con jornada completa del conductor
                jornada_data = []
                hora_entrada = calcular_hora_entrada(v['servicios_asignados'])
                
                # Fila de entrada
                jornada_data.append({
                    'Hora': hora_entrada,
                    'Actividad': 'ENTRADA - Inicio Jornada',
                    'Paciente': '-',
                    'Recogida': '-',
                    'Destino': '-',
                    'Tipo Servicio': '-',
                    'Observaciones': f'Conductor: {v.get("conductor", "N/A")} | Vehículo: {v["id"]} | Matrícula: {v.get("matricula", "N/A")}'
                })
                
                # Servicios del día
                for i, servicio in enumerate(v['servicios_asignados'], 1):
                    jornada_data.append({
                        'Hora': servicio['Hora Cita'],
                        'Actividad': f'SERVICIO #{i}',
                        'Paciente': servicio['Paciente'],
                        'Recogida': servicio['Recogida'],
                        'Destino': servicio['Destino'],
                        'Tipo Servicio': servicio['Tipo'],
                        'Observaciones': f"Inicio: {servicio['Inicio Real']} | Fin: {servicio['Fin Servicio']} | Viaje: {servicio.get('Tiempo Viaje', 0)} min"
                    })
                
                # Fila de salida
                hora_salida = v['servicios_asignados'][-1]['Fin Servicio']
                total_horas = round(v['tiempo_trabajado'] / 60, 2)
                jornada_data.append({
                    'Hora': hora_salida,
                    'Actividad': 'SALIDA - Fin Jornada',
                    'Paciente': '-',
                    'Recogida': '-',
                    'Destino': '-',
                    'Tipo Servicio': '-',
                    'Observaciones': f'Total jornada: {total_horas}h | Servicios realizados: {len(v["servicios_asignados"])}'
                })
                
                df_jornada = pd.DataFrame(jornada_data)
                df_jornada.to_excel(writer, index=False, sheet_name=conductor_nombre)
        
        # Hoja de estadísticas
        if resumen_conductores:
            df_stats = pd.DataFrame(resumen_conductores)
            df_stats.to_excel(writer, index=False, sheet_name='Estadísticas')
    
    buffer.seek(0)
    
    st.download_button(
        label="📈 Descargar Excel PRO con Jornadas Completas",
        data=buffer.getvalue(),
        file_name=f"rutas_optimizadas_PRO_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.success("✅ ¡Excel listo! Incluye hojas individuales por conductor con jornada completa (entrada, servicios, salida)")

# ==========================================
# FOOTER
# ==========================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
🏆 <b>Gestor Inteligente de Flota PRO</b> | Versión 2.0<br>
Optimizado con IA para máxima eficiencia
</div>
""", unsafe_allow_html=True)
