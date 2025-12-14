import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta, time
import io

# ==========================================
# 1. CONFIGURACIÓN Y CLASES
# ==========================================
st.set_page_config(page_title="AmbuSmart v5.0", page_icon="🚑", layout="wide")

# Estilos CSS
st.markdown("""
    <style>
    .stMetric { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #e9ecef; }
    .success-box { padding: 10px; background-color: #d4edda; color: #155724; border-radius: 5px; margin-bottom: 10px; }
    .header-style { font-size: 24px; font-weight: bold; color: #2c3e50; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

# Constantes
BASE_LOCATION = "Hospital Santa Bárbara"
TIEMPO_SERVICIO = 15  # Minutos que tarda en subir/bajar paciente
SHIFT_START = "08:00"
SHIFT_END = "16:00"

# Ubicaciones de Soria (Simulación) y distancias relativas en minutos
LOCATIONS_DB = [
    "Hospital Santa Bárbara", "Centro de Salud La Milagrosa", "Residencia Los Royales",
    "Plaza Mayor Soria", "Estación de Autobuses", "Polígono Las Casas", 
    "Almazán (Centro)", "El Burgo de Osma", "Ólvega", "San Leonardo"
]

class Ambulancia:
    def __init__(self, id_veh, tipo, caps):
        self.id = id_veh
        self.tipo = tipo
        self.caps = caps # {'camilla': 1, 'silla': 1, ...}
        
        # Estado Inicial
        self.timeline = [] # Lista de servicios realizados
        self.last_location = BASE_LOCATION
        self.available_at = datetime.strptime(SHIFT_START, "%H:%M")
        
    def puede_atender(self, tipo_paciente, hora_cita, duracion_estimada):
        """
        Verifica 3 cosas:
        1. Capacidad técnica (Camilla/UVI en Tipo B)
        2. Tiempo para llegar desde la última ubicación
        3. Que termine dentro de la jornada
        """
        # 1. Chequeo Técnico
        req_camilla = 1 if tipo_paciente in ['Camilla', 'UVI'] else 0
        req_silla = 1 if tipo_paciente == 'Silla' else 0
        
        if req_camilla > self.caps['camilla']: return False, 0
        if req_silla > self.caps['silla']: return False, 0
        
        # 2. Chequeo Temporal
        # Simulación de tiempo de viaje: Si es la misma loc, 0 min, si no, random 15-30
        tiempo_traslado = 0 if self.last_location == "Variable" else random.randint(15, 30)
        
        # Hora a la que llegaría a la recogida
        hora_llegada_recogida = self.available_at + timedelta(minutes=tiempo_traslado)
        
        # Margen de tolerancia: Puede llegar hasta 15 min antes, pero no tarde
        # Convertimos a datetime para comparar
        cita_dt = hora_cita # Ya viene como datetime
        
        # Lógica estricta: Debe llegar antes o justo a tiempo (con 5 min de cortesía)
        if hora_llegada_recogida > cita_dt + timedelta(minutes=10):
            return False, 0 # Llega tarde
            
        # 3. Chequeo Jornada (Cierre 16:00)
        fin_jornada = datetime.strptime(SHIFT_END, "%H:%M").replace(
            year=cita_dt.year, month=cita_dt.month, day=cita_dt.day
        )
        
        hora_fin_servicio = hora_llegada_recogida + timedelta(minutes=TIEMPO_SERVICIO + duracion_estimada + TIEMPO_SERVICIO)
        
        if hora_fin_servicio > fin_jornada:
            return False, 0 # Se pasa de turno
            
        return True, tiempo_traslado

    def asignar_servicio(self, paciente, tiempo_traslado):
        # Calcular tiempos finales
        llegada_recogida = self.available_at + timedelta(minutes=tiempo_traslado)
        # Si llega muy pronto, espera hasta la hora de la cita
        inicio_real = max(llegada_recogida, paciente['Hora_dt'])
        
        fin_servicio = inicio_real + timedelta(minutes=TIEMPO_SERVICIO + paciente['Duracion'] + TIEMPO_SERVICIO)
        
        # Registrar en timeline
        registro = {
            'Hora Cita': paciente['Hora'],
            'Paciente': paciente['Paciente'],
            'Recogida': paciente['Recogida'],
            'Destino': paciente['Destino'],
            'Tipo': paciente['Tipo'],
            'Inicio Viaje (Salida anterior)': self.available_at.strftime("%H:%M"),
            'Llegada Recogida': inicio_real.strftime("%H:%M"),
            'Fin Servicio': fin_servicio.strftime("%H:%M"),
            'Estado': 'Completado'
        }
        self.timeline.append(registro)
        
        # Actualizar estado vehículo
        self.available_at = fin_servicio
        self.last_location = paciente['Destino']

# ==========================================
# 2. GENERADOR DE DATOS
# ==========================================
def generar_dataset_prueba(num_servicios=100):
    tipos = ['Sentado'] * 40 + ['Silla'] * 30 + ['Camilla'] * 20 + ['UVI'] * 10
    nombres = ["Juan", "Maria", "Pedro", "Luis", "Ana", "Carmen", "Jose", "Antonio", "Elena", "Isabel"]
    apellidos = ["Garcia", "Lopez", "Perez", "Gonzalez", "Sanz", "Ruiz", "Hernandez", "Jimenez"]
    
    data = []
    start_dt = datetime.strptime(SHIFT_START, "%H:%M")
    
    for i in range(num_servicios):
        # Hora aleatoria entre 08:00 y 15:00 (para que dé tiempo a terminar)
        minutos_rand = random.randint(0, 420) 
        hora_cita = start_dt + timedelta(minutes=minutos_rand)
        
        origen = random.choice(LOCATIONS_DB)
        destino = random.choice([l for l in LOCATIONS_DB if l != origen])
        
        row = {
            'ID': i+1,
            'Hora': hora_cita.strftime("%H:%M"),
            'Paciente': f"{random.choice(nombres)} {random.choice(apellidos)}",
            'Recogida': origen,
            'Destino': destino,
            'Tipo': random.choice(tipos),
            'Duracion': random.randint(20, 45) # Minutos de trayecto puro
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    df = df.sort_values('Hora') # CRÍTICO: Ordenar por hora para el algoritmo
    return df

# ==========================================
# 3. INTERFAZ PRINCIPAL
# ==========================================
st.markdown('<div class="header-style">🚑 AmbuSmart v5.0 - Optimizador Inteligente</div>', unsafe_allow_html=True)

# --- SIDEBAR: FLOTA ---
with st.sidebar:
    st.header("Configuración de Flota")
    st.info("**Vehículos Tipo A (5):**\n2 Sillas + 4 Sentados")
    st.info("**Vehículos Tipo B (18):**\n1 Camilla/UVI + 1 Silla + 5 Sentados")
    
    modo = st.radio("Modo de Operación", ["Generar Prueba (100 pax)", "Cargar Excel Real"])

# --- LÓGICA ---
df_input = None

if modo == "Generar Prueba (100 pax)":
    if st.button("🔄 Generar 100 Servicios Aleatorios"):
        df_input = generar_dataset_prueba(100)
        st.session_state['data'] = df_input
        st.success("Dataset generado correctamente. Revisa la tabla abajo.")
    elif 'data' in st.session_state:
        df_input = st.session_state['data']

else:
    uploaded = st.file_uploader("Sube Excel (Columnas: Hora, Paciente, Recogida, Destino, Tipo, Duracion)", type="xlsx")
    if uploaded:
        df_input = pd.read_excel(uploaded)
        # Asegurar formato hora string
        df_input['Hora'] = df_input['Hora'].apply(lambda x: x.strftime("%H:%M") if isinstance(x, time) else str(x))

# --- VISUALIZACIÓN Y PROCESAMIENTO ---
if df_input is not None:
    st.subheader("1. Listado de Servicios Pendientes")
    st.dataframe(df_input.head(), use_container_width=True)
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.write("")
        st.write("")
        btn_optimizar = st.button("🚀 OPTIMIZAR RUTAS", type="primary", use_container_width=True)

    if btn_optimizar:
        with st.status("Ejecutando Algoritmo Inteligente...", expanded=True) as status:
            
            # 1. CREAR FLOTA DE OBJETOS
            status.write("🛠️ Inicializando Flota (A: 001-005, B: 001-018)...")
            flota = []
            
            # Tipo A
            for i in range(1, 6):
                flota.append(Ambulancia(f"A-{str(i).zfill(3)}", "A", {'camilla':0, 'silla':2, 'sentado':4}))
            # Tipo B
            for i in range(1, 19):
                flota.append(Ambulancia(f"B-{str(i).zfill(3)}", "B", {'camilla':1, 'silla':1, 'sentado':5}))
            
            # 2. ALGORITMO DE ASIGNACIÓN (GREEDY)
            status.write("🧠 Calculando viabilidad tiempo/distancia para cada paciente...")
            
            no_asignados = []
            start_base_dt = datetime.strptime(SHIFT_START, "%H:%M") # Referencia fecha hoy
            
            progress = st.progress(0)
            
            for idx, row in df_input.iterrows():
                # Convertir hora string a dt hoy
                h_str = row['Hora']
                h_obj = datetime.strptime(h_str, "%H:%M")
                row_dt = start_base_dt.replace(hour=h_obj.hour, minute=h_obj.minute)
                
                paciente_obj = row.to_dict()
                paciente_obj['Hora_dt'] = row_dt
                
                asignado = False
                
                # ESTRATEGIA: Buscar el PRIMER vehículo disponible que cumpla condiciones
                # Esto maximiza la ocupación de los primeros vehículos y deja libres los últimos para emergencias
                for veh in flota:
                    puede, t_traslado = veh.puede_atender(row['Tipo'], row_dt, row['Duracion'])
                    
                    if puede:
                        veh.asignar_servicio(paciente_obj, t_traslado)
                        asignado = True
                        break # Pasamos al siguiente paciente
                
                if not asignado:
                    no_asignados.append(row)
                
                progress.progress((idx + 1) / len(df_input))
            
            status.update(label="¡Optimización Finalizada!", state="complete", expanded=False)

        # ==========================================
        # 4. RESULTADOS Y EXPORTACIÓN
        # ==========================================
        st.divider()
        st.header("2. Resultados de la Optimización")
        
        # Métricas
        total_pax = len(df_input)
        total_fail = len(no_asignados)
        total_ok = total_pax - total_fail
        vehiculos_usados = [v for v in flota if len(v.timeline) > 0]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Servicios Asignados", f"{total_ok} / {total_pax}", delta_color="normal")
        m2.metric("Vehículos Activados", f"{len(vehiculos_usados)} / 23")
        m3.metric("Tasa de Éxito", f"{round((total_ok/total_pax)*100, 1)}%")
        
        if total_fail > 0:
            st.error(f"⚠️ {total_fail} Servicios no pudieron asignarse (falta de flota a esa hora o fin de jornada).")
            with st.expander("Ver No Asignados"):
                st.dataframe(pd.DataFrame(no_asignados))
        else:
            st.success("✅ ¡Éxito total! Todos los pacientes tienen ruta asignada.")

        # --- GENERACIÓN DE EXCEL ---
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        
        # Hoja 1: Resumen General
        resumen_gral = []
        for v in vehiculos_usados:
            for s in v.timeline:
                s['Vehículo'] = v.id
                resumen_gral.append(s)
        
        df_resumen = pd.DataFrame(resumen_gral)
        if not df_resumen.empty:
            # Reordenar columnas
            cols = ['Hora Cita', 'Vehículo', 'Paciente', 'Tipo', 'Recogida', 'Destino', 'Llegada Recogida', 'Fin Servicio']
            df_resumen = df_resumen[cols]
            df_resumen.to_excel(writer, sheet_name='Resumen General', index=False)
        
        # Hojas Individuales por Vehículo
        for v in vehiculos_usados:
            df_v = pd.DataFrame(v.timeline)
            df_v.to_excel(writer, sheet_name=v.id, index=False)
            
        writer.close()
        processed_data = output.getvalue()
        
        st.download_button(
            label="📥 Descargar Reporte Profesional (Excel)",
            data=processed_data,
            file_name="Reporte_Rutas_Ambulancias.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        
        # Visualización Rápida
        st.subheader("Vista Previa por Vehículo")
        v_sel = st.selectbox("Seleccionar Vehículo", [v.id for v in vehiculos_usados])
        v_obj = next((v for v in vehiculos_usados if v.id == v_sel), None)
        if v_obj:
            st.table(pd.DataFrame(v_obj.timeline)[['Hora Cita', 'Paciente', 'Tipo', 'Recogida', 'Fin Servicio']])

elif df_input is None:
    st.info("👈 Selecciona una opción en el menú lateral para comenzar.")
