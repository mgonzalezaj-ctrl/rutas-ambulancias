# ==========================================
# GESTOR INTELIGENTE DE FLOTA DE AMBULANCIAS PRO V3.0
# Versión Optimizada - Múltiples Servicios por Conductor
# ==========================================

import streamlit as st
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import io
from collections import defaultdict
import math
import pdfplumber

# ==========================================
# CONFIGURACIÓN
# ==========================================

st.set_page_config(
    page_title="🏆 Gestor Pro de Flota",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🏆 Gestor Inteligente de Flota V3.0 - OPTIMIZADO")
st.markdown("""### Sistema con Múltiples Servicios por Conductor
**Mejoras V3.0:**
- 🚗 4 Bases: Soria, Almazán, Burgo de Osma, Ólvega
- 🎯 Múltiples servicios por conductor (hasta 10h)
- 🧠 Optimización inteligente de vehículos
- 📊 Agrupación geográfica mejorada
---
""")

# Configuración
DURACION_SERVICIO = 60
JORNADA_MAX = 10 * 60
MARGEN_TIEMPO = 30

# Bases geográficas con coordenadas
BASES = {
    'Soria': {'lat': 41.7665, 'lon': -2.4790},
    'Almazán': {'lat': 41.4856, 'lon': -2.5252},
    'Burgo de Osma': {'lat': 41.5869, 'lon': -3.0661},
    'Ólvega': {'lat': 41.7974, 'lon': -2.0306, 'solo_tarde': True}
}

# Función para calcular distancia real
def calcular_distancia_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def asignar_base_mas_cercana(ubicacion):
    mejor_base = 'Soria'
    min_dist = float('inf')
    for base, coords in BASES.items():
        if 'Almazán' in str(ubicacion):
            return 'Almazán'
        if 'Burgo' in str(ubicacion) or 'Osma' in str(ubicacion):
            return 'Burgo de Osma'
        if 'Ólvega' in str(ubicacion):
            return 'Ólvega'
    return 'Soria'

def puede_llevar(vehiculo_tipo, paciente_tipo):
    if vehiculo_tipo == "A":
        return paciente_tipo in ["Sentado", "Silla"]
    return True

def calcular_hora_entrada(servicios):
    if not servicios:
        return "08:00"
    try:
        primer_servicio = min(servicios, key=lambda x: pd.to_datetime(str(x.get('Hora Cita', '08:00')), errors='coerce'))
        hora_cita = pd.to_datetime(str(primer_servicio.get('Hora Cita', '08:00')), errors='coerce')
        hora_entrada = hora_cita - timedelta(minutes=45)
        return hora_entrada.strftime("%H:%M")
    except:
        return "08:00"

# ==========================================
# ALGORITMO DE OPTIMIZACIÓN MEJORADO
# ==========================================

def optimizar_rutas_multiple_servicios(df_servicios, flota):
    resultados = []
    
    # Ordenar servicios por hora
    df_servicios = df_servicios.sort_values('Hora Cita')
    
    # Asignar base a cada servicio
    df_servicios['Base'] = df_servicios['Recogida'].apply(asignar_base_mas_cercana)
    
    # Agrupar servicios por bloques horarios
    servicios_pendientes = df_servicios.to_dict('records')
    
    for vehiculo in flota:
        vehiculo['disponible_desde'] = datetime.strptime("08:00", "%H:%M")
        vehiculo['servicios_asignados'] = []
        vehiculo['tiempo_trabajado'] = 0
        vehiculo['base'] = 'Soria'
    
    # Asignar múltiples servicios por conductor
    for servicio in servicios_pendientes:
        try:
            hora_cita = pd.to_datetime(str(servicio['Hora Cita']), errors='coerce')
            if pd.isna(hora_cita):
                hora_cita = pd.to_datetime(f"2000-01-01 {servicio['Hora Cita']}", errors='coerce')
            
            ventana_inicio = hora_cita - timedelta(minutes=MARGEN_TIEMPO)
            ventana_fin = hora_cita + timedelta(minutes=MARGEN_TIEMPO)
            
            # Buscar vehículo disponible que pueda llevar este servicio
            candidatos = [v for v in flota if puede_llevar(v['tipo'], servicio.get('Tipo', 'Sentado'))]
            
            # Filtrar candidatos que aún tienen tiempo disponible
            candidatos = [c for c in candidatos if c['tiempo_trabajado'] < JORNADA_MAX]
            
            # Ordenar por: 1) menos tiempo trabajado, 2) más servicios (para agrupar)
            candidatos.sort(key=lambda x: (x['tiempo_trabajado'], -len(x['servicios_asignados'])))
            
            asignado = False
            
            for vehiculo in candidatos:
                tiempo_viaje = 20  # Tiempo base
                
                if vehiculo['servicios_asignados']:
                    # Calcular tiempo desde último servicio
                    tiempo_viaje = 25
                
                hora_disponible = vehiculo['disponible_desde'] + timedelta(minutes=tiempo_viaje)
                inicio_real = max(hora_disponible, ventana_inicio)
                
                # Verificar si puede llegar a tiempo y no supera jornada
                if inicio_real <= ventana_fin:
                    tiempo_servicio = tiempo_viaje + DURACION_SERVICIO
                    nuevo_tiempo = vehiculo['tiempo_trabajado'] + tiempo_servicio
                    
                    if nuevo_tiempo <= JORNADA_MAX:
                        # ASIGNAR SERVICIO
                        fin_real = inicio_real + timedelta(minutes=DURACION_SERVICIO)
                        
                        servicio_info = {
                            'Vehículo': vehiculo['id'],
                            'Conductor': vehiculo.get('conductor', 'N/A'),
                            'Hora Cita': servicio['Hora Cita'],
                            'Inicio Real': inicio_real.strftime("%H:%M"),
                            'Fin Servicio': fin_real.strftime("%H:%M"),
                            'Paciente': servicio['Paciente'],
                            'Recogida': servicio['Recogida'],
                            'Destino': servicio['Destino'],
                            'Tipo': servicio.get('Tipo', 'Sentado'),
                            'Base': servicio.get('Base', 'Soria'),
                            'Tiempo Viaje': int(tiempo_viaje),
                            'Horas Trabajadas': round(nuevo_tiempo / 60, 2)
                        }
                        
                        vehiculo['disponible_desde'] = fin_real
                        vehiculo['tiempo_trabajado'] = nuevo_tiempo
                        vehiculo['servicios_asignados'].append(servicio_info)
                        resultados.append(servicio_info)
                        asignado = True
                        break
            
            if not asignado:
                resultados.append({
                    'Vehículo': 'SIN ASIGNAR',
                    'Conductor': 'N/A',
                    'Hora Cita': servicio['Hora Cita'],
                    'Paciente': servicio['Paciente'],
                    'Recogida': servicio['Recogida'],
                    'Destino': servicio['Destino'],
                    'Tipo': servicio.get('Tipo', 'Sentado')
                })
        
        except Exception as e:
            pass
    
    return pd.DataFrame(resultados), flota

# ==========================================
# GESTIÓN DE FLOTA (SIDEBAR)
# ==========================================

if 'vehiculos_personalizados' not in :
    ['vehiculos_personalizados'] = []

st.sidebar.header("🚗 Gestión de Flota")

    if st.sidebar.button("🚑 Pre-Cargar Flota Manual (35 vehículos)"):  
                ['vehiculos_personalizados'] = []
    
    for i in range(1, 28):
        st.session_state['vehiculos_personalizados'].append({
            "id": f"B-{i:03d}",
            "tipo": "B",
            "conductor": f"Conductor B-{i}",
            st.s"matricula": f"{1000+i}BBB"
        })
    
    for i in range(1, 9):
        ['vehiculos_personalizados'].append({
            "id": f"A-{i:03d}",
            "tipo": "A",
            "conductor": f"Conductor A-{i}",
            "matricula": f"{2000+i}AAA"
        })
    
    st.sidebar.success("✅ Flota cargada: 27 tipo B + 8 tipo A")
    st.rerun()

if st.sidebar.button("🗑️ Limpiar Flota"):
    ['vehiculos_personalizados'] = []
    st.sidebar.warning("⚠️ Flota limpiada")
    st.rerun()

with st.sidebar.expander("➕ Añadir Vehículo", expanded=False):
    with st.form("form_vehiculo"):
        nuevo_id = st.text_input("ID", placeholder="A-001")
        nuevo_tipo = st.selectbox("Tipo", ["A", "B"])
        nuevo_conductor = st.text_input("Conductor")
        nueva_matricula = st.text_input("Matrícula")
        
        if st.form_submit_button("✅ Añadir"):
            if nuevo_id and nuevo_conductor:
                ['vehiculos_personalizados'].append({
                    "id": nuevo_id,
                    "tipo": nuevo_tipo,
                    "conductor": nuevo_conductor,
                    "matricula": nueva_matricula
                })
                st.success(f"✅ {nuevo_id} añadido")

if ['vehiculos_personalizados']:
    st.sidebar.subheader(f"📋 Flota ({len(['vehiculos_personalizados'])} vehículos)")
    for idx, v in enumerate(['vehiculos_personalizados']):
        with st.sidebar.expander(f"{v['id']} - {v['conductor']}"):
            st.write(f"**Tipo:** {v['tipo']}")
            st.write(f"**Matrícula:** {v['matricula']}")
            if st.button(f"🗑️ Eliminar", key=f"del_{idx}"):
                ['vehiculos_personalizados'].pop(idx)
                st.rerun()

# ==========================================
# INTERFAZ PRINCIPAL
# ==========================================

st.subheader("📄 Paso 1: Cargar Servicios")

uploaded_file = st.file_uploader("Sube tu archivo Excel o PDF", type=['xlsx', 'xls', 'pdf'])

if uploaded_file:
    try:
        file_ext = uploaded_file.name.split('.')[-1].lower()
        
        if file_ext == 'pdf':
            with pdfplumber.open(uploaded_file) as pdf:
                table = pdf.pages[0].extract_table()
                if table:
                    df = pd.DataFrame(table[1:], columns=table[0])
                else:
                    st.error("❌ No se encontraron tablas en PDF")
                    df = None
        else:
            df = pd.read_excel(uploaded_file)
        
        if df is not None:
            columnas_req = ['Paciente', 'Hora Cita', 'Recogida', 'Destino', 'Tipo']
            faltantes = [c for c in columnas_req if c not in df.columns]
            
            if faltantes:
                st.error(f"❌ Faltan columnas: {', '.join(faltantes)}")
                st.info("💡 Columnas requeridas: Paciente, Hora Cita, Recogida, Destino, Tipo")
            else:
                ['df_servicios'] = df
                st.success(f"✅ {len(df)} servicios cargados")
    
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")

if 'df_servicios' in :
    df = ['df_servicios']
    st.dataframe(df.head(10), use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Limpiar Servicios"):
            del ['df_servicios']
            if 'df_resultado' in :
                del ['df_resultado']
            st.rerun()
    
    with col2:
        if st.button("🔄 Resetear Resultados"):
            if 'df_resultado' in :
                del ['df_resultado']
            st.rerun()
    
    st.subheader("🚀 Paso 2: Calcular Rutas Optimizadas")
    
    # Botón para calcular rutas (con auto-carga de vehículos si es necesario)
    if st.button("🚀 CALCULAR RUTAS CON OPTIMIZACIÓN"):
                # Si no hay vehículos, crear automáticamente según servicios
        if not st.session_state['vehiculos_personalizados']:            st.info("🤖 Calculando vehículos necesarios automáticamente...")
            # Estimación simple: 1 vehículo por cada 6 servicios, mínimo 10
            num_servicios = len(['df_servicios'])
            num_vehiculos = max(10, (num_servicios // 6) + 1)
            
            # Crear 70% tipo B, 30% tipo A
            num_b = int(num_vehiculos * 0.7)
            num_a = num_vehiculos - num_b
            
            ['vehiculos_personalizados'] = []
            for i in range(1, num_b + 1):
                ['vehiculos_personalizados'].append({
                    "id": f"B-{i:03d}",
                    "tipo": "B",
                    "conductor": f"Conductor B-{i}",
                    "matricula": f"{1000+i}BBB"
                })
            
            for i in range(1, num_a + 1):
                ['vehiculos_personalizados'].append({
                    "id": f"A-{i:03d}",
                    "tipo": "A",
                    "conductor": f"Conductor A-{i}",
                    "matricula": f"{2000+i}AAA"
                })
            
            st.success(f"✅ Flota creada automáticamente: {num_b} tipo B + {num_a} tipo A = {num_vehiculos} total")
        
            with st.spinner("🔄 Optimizando con múltiples servicios por conductor..."):
                flota = [v.copy() for v in ['vehiculos_personalizados']]
                
                df_resultado, flota = optimizar_rutas_multiple_servicios(df, flota)
                ['df_resultado'] = df_resultado
                ['flota'] = flota
                
                st.success("✅ ¡Optimización completada con éxito!")

# ==========================================
# DASHBOARD DE RESULTADOS
# ==========================================

if 'df_resultado' in :
    df_res = ['df_resultado']
    flota = ['flota']
    
    st.subheader("📊 Dashboard de Resultados OPTIMIZADOS")
    
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    
    vehiculos_usados = len([v for v in flota if v['servicios_asignados']])
    servicios_ok = len(df_res[~df_res['Vehículo'].str.contains('SIN', na=False)])
    pendientes = len(df_res) - servicios_ok
    eficiencia = round((servicios_ok/len(df_res))*100, 1) if len(df_res) > 0 else 0
    
    col1.metric("🚑 Vehículos Usados", vehiculos_usados)
    col2.metric("✅ Servicios Asignados", servicios_ok)
    col3.metric("❌ Pendientes", pendientes)
    col4.metric("🎯 Eficiencia", f"{eficiencia}%")
    
    # Resumen por conductor
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
                'Estado': '✅ Óptimo' if total_horas <= 8 else '⚠️ Extendida'
            })
    
    if resumen_conductores:
        df_conductores = pd.DataFrame(resumen_conductores)
        st.dataframe(df_conductores, use_container_width=True)
        
        # Métricas adicionales
        st.info(f"📈 **Promedio de servicios por conductor:** {round(df_conductores['Nº Servicios'].mean(), 1)}")
    
    # Tabla detallada
    st.subheader("📋 Tabla Detallada")
    st.dataframe(df_res, use_container_width=True)
    
    # ==========================================
    # EXPORTACIÓN A EXCEL
    # ==========================================
    
    st.subheader("📥 Exportar Excel Profesional")
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Hoja resumen general
        df_res.to_excel(writer, index=False, sheet_name='Resumen General')
        
        # Hoja por cada conductor
        for v in flota:
            if v['servicios_asignados']:
                conductor_nombre = v.get('conductor', v['id']).replace('/', '-')[:30]
                
                jornada_data = []
                hora_entrada = calcular_hora_entrada(v['servicios_asignados'])
                
                # Entrada
                jornada_data.append({
                    'Hora': hora_entrada,
                    'Actividad': 'ENTRADA',
                    'Paciente': '-',
                    'Recogida': '-',
                    'Destino': '-',
                    'Tipo': '-',
                    'Observaciones': f"Conductor: {v.get('conductor', 'N/A')} | Veh: {v['id']}"
                })
                
                # Servicios
                for i, servicio in enumerate(v['servicios_asignados'], 1):
                    jornada_data.append({
                        'Hora': servicio['Hora Cita'],
                        'Actividad': f'SERVICIO #{i}',
                        'Paciente': servicio['Paciente'],
                        'Recogida': servicio['Recogida'],
                        'Destino': servicio['Destino'],
                        'Tipo': servicio['Tipo'],
                        'Observaciones': f"Inicio: {servicio['Inicio Real']} | Fin: {servicio['Fin Servicio']}"
                    })
                
                # Salida
                hora_salida = v['servicios_asignados'][-1]['Fin Servicio']
                total_horas = round(v['tiempo_trabajado'] / 60, 2)
                jornada_data.append({
                    'Hora': hora_salida,
                    'Actividad': 'SALIDA',
                    'Paciente': '-',
                    'Recogida': '-',
                    'Destino': '-',
                    'Tipo': '-',
                    'Observaciones': f'Total: {total_horas}h | Servicios: {len(v["servicios_asignados"])}'
                })
                
                df_jornada = pd.DataFrame(jornada_data)
                df_jornada.to_excel(writer, index=False, sheet_name=conductor_nombre)
        
        # Estadísticas
        if resumen_conductores:
            df_stats = pd.DataFrame(resumen_conductores)
            df_stats.to_excel(writer, index=False, sheet_name='Estadísticas')
    
    buffer.seek(0)
    
    st.download_button(
        label="📈 DESCARGAR EXCEL OPTIMIZADO",
        data=buffer.getvalue(),
        file_name=f"rutas_optimizadas_V3_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.success("✅ Excel con hojas individuales por conductor listo para descargar")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
🏆 <b>Gestor Inteligente V3.0 OPTIMIZADO</b><br>
Con múltiples servicios por conductor y 4 bases geográficas
</div>
""", unsafe_allow_html=True)





