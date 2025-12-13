import streamlit as st
import pandas as pd
import pdfplumber
import time
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Gestión de Rutas Sanitarias Pro", layout="wide", page_icon="🚑")
st.markdown("""<style>.stButton>button { background-color: #d32f2f; color: white; width: 100%; }</style>""", unsafe_allow_html=True)

st.title("🚑 Sistema Inteligente de Rutas Sanitarias")
st.markdown("**Características:** Multi-Base, Ventanas Horarias, Acompañantes, Jornada 8h y 10min por servicio.")
# --- BASES OPERATIVAS ---
BASES_CONOCIDAS = {
    "Hospital Soria (Central)": (41.7690, -2.4615),
    "Centro Salud Almazán": (41.4835, -2.5317),
    "Centro Salud Burgo de Osma": (41.5878, -3.0664),
    "Centro Salud Ólvega": (41.7795, -1.9841),
    "Otra (Geolocalizar)": None
}

# --- DATOS TÉCNICOS ---
# Definimos capacidades: [Silla, Camilla, Asientos, Aislamiento]
TIPOS_AMBULANCIA = {
    "A (1 Camilla/Silla + 2 Sent)": {"silla":1, "camilla":1, "sentado":2, "aisl":100},
    "B (2 Sillas + 4 Sent)":        {"silla":2, "camilla":0, "sentado":4, "aisl":100},
    "C (7 Sentados - Colectiva)":   {"silla":0, "camilla":0, "sentado":7, "aisl":100},
    "UVI (1 Camilla Exclusiva)":    {"silla":0, "camilla":1, "sentado":1, "aisl":100}
}

# --- BARRA LATERAL (CONFIGURACIÓN FLOTA) ---
with st.sidebar:
    st.header("⚙️ Configuración de Flota")
    num = st.number_input("Nº Ambulancias Máximo (el sistema usará solo las necesarias)", 1, 30, 15)
    FLOTA_CONF = []
    
    for i in range(num):
        with st.expander(f"Vehículo {i+1}", expanded=(i==0)):
            nom = st.text_input("Matrícula/ID", f"AMB-{101+i}", key=f"n{i}")
            tipo = st.selectbox("Tipo", list(TIPOS_AMBULANCIA.keys()), key=f"t{i}")
            base_nombre = st.selectbox("Base de Salida", list(BASES_CONOCIDAS.keys()), key=f"b{i}")
            
            base_coords = BASES_CONOCIDAS[base_nombre]
            if base_nombre == "Otra (Geolocalizar)":
                dir_manual = st.text_input("Dirección base", "Calle...", key=f"bm{i}")
                base_coords = "MANUAL:" + dir_manual
            
            FLOTA_CONF.append({
                "nombre": nom,
                "caps": TIPOS_AMBULANCIA[tipo],
                "base_coords": base_coords,
                "base_nombre": base_nombre
            })

# --- FUNCIONES AUXILIARES ---
def leer_pdf(f):
    try:
        with pdfplumber.open(f) as pdf:
            data = []
            for p in pdf.pages:
                tbl = p.extract_tables()
                for t in tbl: data.extend(t[1:] if not data else t)
            return pd.DataFrame(data[1:], columns=data[0]) if data else None
    except: return None

def geocode(d, geo):
    try: 
        # Pequeña pausa para no saturar el servidor de mapas gratuito
        time.sleep(0.6) 
        return (geo.geocode(d if "España" in d else d+", España", timeout=10).point[:2])
    except: return None

def time_to_min(t_str):
    """Convierte HH:MM a minutos del día"""
    try:
        if pd.isna(t_str) or str(t_str).strip() == "": return None
        t_str = str(t_str).strip()
        if " " in t_str: t_str = t_str.split(" ")[1] # Si viene formato fecha
        h, m = map(int, t_str.split(":")[:2])
        return h * 60 + m
    except: return None

def min_to_hhmm(m):
    """Convierte minutos del día a HH:MM"""
    h = int(m // 60)
    mn = int(m % 60)
    return f"{h:02d}:{mn:02d}"

# --- LÓGICA PRINCIPAL (CÁLCULO) ---
def calcular(df, flota_config):
    geo = Nominatim(user_agent="app_rutas_sanitarias_final_v1")
    prog = st.progress(0)
    st.info("📡 Geolocalizando direcciones y calculando restricciones...")
    
    # --- PARÁMETROS DE OPERACIÓN ---
    VELOCIDAD_MEDIA = 55.0  # km/h (Conservador para carreteras secundarias)
    TIEMPO_SERVICIO = 10    # min por parada (subir/bajar paciente)
    HORA_INICIO = 8 * 60    # 08:00 AM
    HORA_FIN = 22 * 60      # 22:00 PM
    
    # Factor de tolerancia para "Tiempo Máximo de Viaje"
    # Un viaje no puede durar más que: (Tiempo Directo * 1.5) + 30 min
    FACTOR_MAX_TIEMPO = 3.0 
    BUFFER_MAX_TIEMPO = 90 

    # 1. Procesar Pacientes
    pacientes_puntos = []
    nombres = []
        direcciones_pacientes = []  # [(dir_recogida, dir_destino), ...]
    # Demandas separadas por tipo
    dem = {"silla":[], "camilla":[], "sentado":[], "aisl":[]}
    time_windows = [] 
    pairs = []
    map_d = []
    
    total_rows = len(df)
    
    for i, r in enumerate(df):
        prog.progress((i/total_rows)*0.9)
        
        # Geolocalizar
        orig = geocode(r.get("Recogida"), geo)
        dest = geocode(r.get("Destino"), geo)
        
        if orig and dest:
            idx = len(pacientes_puntos) # Índice del nodo de recogida
            pacientes_puntos.extend([orig, dest])
            
            # Datos básicos
            nom = r.get("Paciente", "?")
            hora_cita = time_to_min(r.get("Hora"))
            tiene_acomp = str(r.get("Acompañante", "")).upper() == "SI"
            
            # Textos para visualización
            hora_txt = r.get("Hora", "Flexible") if r.get("Hora") else "Flexible"
            acomp_txt = " + Acompañante" if tiene_acomp else ""
            
            nombres.extend([
                f"RECOGER: {nom}{acomp_txt}", 
                f"ENTREGAR: {nom} ({hora_txt})"
            ])

                # Guardar direcciones originales
                        direcciones_pacientes.extend([
                                            (r.get("Recogida", ""), r.get("Destino", "")),
                                            (r.get("Recogida", ""), r.get("Destino", ""))
                                        ])
            
            # Mapa (Verde=Origen, Rojo=Destino)
            map_d.extend([
                {"lat":orig[0], "lon":orig[1], "color":"#00FF00"},
                {"lat":dest[0], "lon":dest[1], "color":"#FF0000"}
            ])
            
            # --- CÁLCULO DE CAPACIDADES ---
            tipo_req = str(r.get("Tipo", "")).upper()
            req_silla = "SILLA" in tipo_req
            req_camilla = "CAMILLA" in tipo_req
            req_aisl = "AISL" in tipo_req
            req_sentado = "SENTADO" in tipo_req
            
            # Lógica Acompañante: Ocupa un asiento normal.
            # Si el paciente va en Silla, necesitamos 1 hueco silla + 1 asiento.
            # Si el paciente va Sentado, necesitamos 1 asiento + 1 asiento.
            demanda_silla = 1 if req_silla else 0
            demanda_camilla = 1 if req_camilla else 0
            demanda_aisl = 1 if req_aisl else 0
            
            # El asiento base del paciente (si no es camilla/silla) + asiento acompañante
            asientos_necesarios = 0
            if req_sentado: asientos_necesarios += 1
            if tiene_acomp: asientos_necesarios += 1
            
            # Llenar arrays de demanda (+ en origen, - en destino)
            dem["silla"].extend([demanda_silla, -demanda_silla])
            dem["camilla"].extend([demanda_camilla, -demanda_camilla])
            dem["aisl"].extend([demanda_aisl, -demanda_aisl])
            dem["sentado"].extend([asientos_necesarios, -asientos_necesarios])
            
            # --- VENTANAS DE TIEMPO ---
            # Nodo Recogida (Flexible, pero dentro del turno)
            time_windows.append((HORA_INICIO, HORA_FIN))
            
            # Nodo Entrega
            if hora_cita:
                # Llegada permitida: entre 45 min antes y la hora exacta
                time_windows.append((max(HORA_INICIO, hora_cita - 60), hora_cita))
            else:
                time_windows.append((HORA_INICIO, HORA_FIN))
            
            # Registrar par (Pickup -> Delivery)
            pairs.append([idx, idx+1])

    # 2. Procesar Bases y Flota
    veh_coords = []
    veh_caps = {"silla":[], "camilla":[], "sentado":[], "aisl":[]}
    
    for v in flota_config:
        coords = v["base_coords"]
        if isinstance(coords, str) and coords.startswith("MANUAL:"):
            c = geocode(coords.replace("MANUAL:", ""), geo)
            coords = c if c else BASES_CONOCIDAS["Hospital Soria (Central)"]
        veh_coords.append(coords)
        
        for k in veh_caps: veh_caps[k].append(v["caps"][k])

    if not pacientes_puntos:
        st.error("❌ No se pudieron geolocalizar pacientes. Verifica direcciones.")
        return

    # 3. Matrices de Distancia y Tiempo
    all_points = pacientes_puntos + veh_coords
    num_nodos = len(all_points)
    num_vehiculos = len(flota_config)
    
    # Índices de Bases
    base_indices = [len(pacientes_puntos) + i for i in range(num_vehiculos)]
    starts = base_indices
    ends = base_indices

    dist_matrix = {}
    time_matrix = {}
    
    for i in range(num_nodos):
        dist_matrix[i] = {}
        time_matrix[i] = {}
        for j in range(num_nodos):
            if i == j: 
                dist_matrix[i][j] = 0
                time_matrix[i][j] = 0
            else:
                d_m = geodesic(all_points[i], all_points[j]).meters
                dist_matrix[i][j] = int(d_m)
                
                # Tiempo (min) = (km / v) * 60
                travel_time = (d_m / 1000 / VELOCIDAD_MEDIA) * 60
                
                # Tiempo de servicio en ORIGEN (si es paciente)
                service_time = TIEMPO_SERVICIO if i < len(pacientes_puntos) else 0
                time_matrix[i][j] = int(travel_time + service_time)

    # 4. Configurar OR-Tools
    manager = pywrapcp.RoutingIndexManager(num_nodos, num_vehiculos, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    # Callback de Tiempo (Coste Principal)
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return time_matrix[from_node][to_node]

    transit_cb = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    # Dimensión Tiempo
    routing.AddDimension(
        transit_cb,
        60,    # Slack (espera máx permitida en puerta)
        24*60, # Horizonte máx
        False, 
        "Time"
    )
    time_dim = routing.GetDimensionOrDie("Time")

    # Restricciones de Ventana Horaria
    for i in range(num_nodos):
        index = manager.NodeToIndex(i)
        if i < len(time_windows): # Pacientes
            start, end = time_windows[i]
            time_dim.CumulVar(index).SetRange(int(start), int(end))
        else: # Bases
            time_dim.CumulVar(index).SetRange(HORA_INICIO, HORA_FIN)

            # Límite de jornada laboral: 8 horas máximo por ambulancia
                MAX_JORNADA = 8 * 60  # 480 minutos = 8 horas
                for vehicle_id in range(num_vehiculos):
                            start_idx = routing.Start(vehicle_id)
                            end_idx = routing.End(vehicle_id)
                            routing.solver().Add(
                                            time_dim.CumulVar(end_idx) - time_dim.CumulVar(start_idx) <= MAX_JORNADA
                                        )

    # Dimensiones Capacidad (Silla, Camilla, etc)
    for k in veh_caps:
        def demand_cb(from_index):
            node = manager.IndexToNode(from_index)
            if node >= len(dem[k]): return 0
            return dem[k][node]
        
        idx_cb = routing.RegisterUnaryTransitCallback(demand_cb)
        routing.AddDimensionWithVehicleCapacity(idx_cb, 0, veh_caps[k], True, f"Cap_{k}")

    # --- RESTRICCIONES COMPLEJAS ---
    solver = routing.solver()
    
    for request in pairs:
        p_idx = manager.NodeToIndex(request[0])
        d_idx = manager.NodeToIndex(request[1])
        
        # RESTRICCIÓN DESACTIVADA: Permite diferentes ambulancias para recogida/entrega
        # 
# RESTRICCIÓN DESACTIVADA: Sin límite de tiempo máximo en ruta
        #             time_dim.CumulVar(d_idx) - time_dim.CumulVar(p_idx) <= max_viaje + TIEMPO_SERVICIO
    

    # 5. Resolver
    st.info("🧠 Optimizando rutas (esto puede tardar unos segundos)...")
    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.time_limit.seconds = 30 # Damos un poco más de tiempo por la complejidad

    solution = routing.SolveWithParameters(search_params)
    prog.progress(100)

    # 6. Resultados y Exportación
    if solution:
        st.success("✅ ¡Rutas calculadas con éxito!")
        
        # Mapa General
        st.map(pd.DataFrame(map_d))
        
        export_data = [] # Lista para el CSV final

        cols = st.columns(min(num_vehiculos, 3))
        
        for vehicle_id in range(num_vehiculos):
            index = routing.Start(vehicle_id)
            veh_name = flota_config[vehicle_id]['nombre']
            route_text = []
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                
                # Tiempo
                time_var = time_dim.CumulVar(index)
                t_val = solution.Min(time_var)
                t_str = min_to_hhmm(t_val)
                            
            # Capturar la primera hora (hora de inicio del turno)
            if hora_inicio is None:
                hora_inicio = t_val
                
                # Nombre del paso
                if node_index >= len(nombres):
                    base_n = flota_config[vehicle_id]['base_nombre']
                    step_desc = f"BASE ({base_n})"
                    step_ui = f"🏠 **{t_str}** - Salida Base {base_n}"
                else:
            step_desc = nombres[node_index]
                
                # Obtener dirección completa del paciente
                if node_index < len(direcciones_pacientes):
                    dir_origen, dir_destino = direcciones_pacientes[node_index]
                else:
                    dir_origen, dir_destino = "", ""
                
                if "RECOGER" in step_desc:
                    icon = "🟢"
                    # Extraer solo el nombre del paciente (sin "RECOGER:")
                    nombre_paciente = step_desc.replace("RECOGER: ", "")
                    step_ui = f"{icon} **{t_str}** - RECOGER: {nombre_paciente} en {dir_origen}"
                else:  # ENTREGAR
                    icon = "🔴"
                    # Extraer nombre del paciente (sin "ENTREGAR:" y hora entre paréntesis)
                    nombre_paciente = step_desc.replace("ENTREGAR: ", "").split(" (")[0]
                    step_ui = f"{icon} **{t_str}** - ENTREGAR: {nombre_paciente} en {dir_destino}"                
                route_text.append(step_ui)
                
                # Guardar para Excel
                export_data.append({
                    "Ambulancia": veh_name,
                    "Hora Estimada": t_str,
                    "Actividad": step_desc,
                    "Orden": len(route_text)
                })
                
                index = solution.Value(routing.NextVar(index))
            
            # Fin de ruta
            time_var = time_dim.CumulVar(index)
            t_str = min_to_hhmm(solution.Min(time_var))
        # Calcular horas totales trabajadas
            hora_fin = solution.Min(time_var)
            if hora_inicio is not None:
                horas_trabajadas = (hora_fin - hora_inicio) / 60  # Convertir minutos a horas
                route_text.append(f"🏁 **{t_str}** - Fin de Servicio (Total trabajado: {horas_trabajadas:.1f}h)")
            else:
                route_text.append(f"🏁 **{t_str}** - Fin de Servicio")            export_data.append({"Ambulancia": veh_name, "Hora Estimada": t_str, "Actividad": "FIN DE TURNO", "Orden": 999})

            # Mostrar tarjeta en pantalla
            with st.expander(f"🚑 {veh_name}", expanded=True):
                if len(route_text) <= 2:
                    st.caption("Sin servicios asignados.")
                else:
                    for line in route_text: st.markdown(line)

        # --- SECCIÓN DE DESCARGA ---
        st.markdown("### 📥 Descargas para Conductores")
        df_export = pd.DataFrame(export_data)
        csv = df_export.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📄 Descargar Hoja de Ruta (CSV/Excel)",
            data=csv,
            file_name="hoja_de_ruta_optimizada.csv",
            mime="text/csv"
        )
        
    else:
        st.error("⚠️ No se encontró solución. Posibles causas:")
        st.markdown("""
        1. **Horarios imposibles:** Un paciente necesita estar a las 10:00 en un sitio muy lejano.
        2. **Falta de vehículos:** Hay más camillas/sillas que ambulancias disponibles.
        3. **Tiempo Máximo:** La restricción de no tener al paciente paseando es muy estricta.
        """)

# --- INTERFAZ DE CARGA ---
st.markdown("---")
uploaded_file = st.file_uploader("Cargar Archivo de Pacientes (Excel/PDF)", type=["xlsx", "pdf"])

if uploaded_file and st.button("🚀 Calcular Rutas"):
    if uploaded_file.name.endswith('.xlsx'):
        df = pd.read_excel(uploaded_file)
    else:
        df = leer_pdf(uploaded_file)
        
    if df is not None:
        # Normalizar columnas (quitar espacios, mayúsculas primera letra)
        df.columns = [c.strip().title() for c in df.columns]
        
        req_cols = ["Paciente", "Recogida", "Destino", "Tipo"]
        if not all(col in df.columns for col in req_cols):
            st.error(f"Faltan columnas obligatorias. Tu archivo debe tener: {req_cols}")
        else:
            st.success("Archivo cargado correctamente.")
            st.dataframe(df.head())

            calcular(df.to_dict('records'), FLOTA_CONF)







