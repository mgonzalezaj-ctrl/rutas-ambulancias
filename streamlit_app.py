import streamlit as st
import pandas as pd
import numpy as np
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.distance import geodesic
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import time
from datetime import datetime, timedelta
import io

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Optimización Rutas Ambulancias",
    page_icon="🚑",
    layout="wide"
)

# ==========================================
# CLASES Y CONFIGURACIÓN
# ==========================================

class Ambulancia:
    def __init__(self, tipo, capacidad, cantidad):
        self.tipo = tipo
        self.capacidad = capacidad
        self.cantidad = cantidad

def haversine_time(coord1, coord2, speed_kmh=40):
    """
    Calcula el tiempo estimado en minutos entre dos coordenadas
    asumiendo una velocidad media constante (distancia Haversine).
    """
    if not coord1 or not coord2:
        return 999999  # Penalización alta si falta coord
    
    dist_km = geodesic(coord1, coord2).km
    # Tiempo = Distancia / Velocidad * 60 min
    minutes = (dist_km / speed_kmh) * 60
    return int(minutes + 1)  # +1 para ser conservador y redondear arriba

@st.cache_data
def geocode_address(address):
    """
    Geocodifica una dirección usando Nominatim con caché de Streamlit.
    """
    geolocator = Nominatim(user_agent="ambulance_optimizer_app_v1")
    try:
        # Añadimos un pequeño sleep para respetar la política de uso de Nominatim
        time.sleep(1.1) 
        location = geolocator.geocode(address)
        if location:
            return (location.latitude, location.longitude)
        return None
    except Exception as e:
        return None

# ==========================================
# LÓGICA DE OR-TOOLS
# ==========================================

def create_data_model(locations, capacities, time_windows, num_vehicles, depot_index=0):
    """Crea el modelo de datos para OR-Tools."""
    data = {}
    
    # 1. Matriz de Tiempos (minutos)
    num_locations = len(locations)
    time_matrix = [[0] * num_locations for _ in range(num_locations)]
    
    for i in range(num_locations):
        for j in range(num_locations):
            if i == j:
                time_matrix[i][j] = 0
            else:
                # Calculamos tiempo de viaje estimado
                time_matrix[i][j] = haversine_time(locations[i], locations[j])
    
    data['time_matrix'] = time_matrix
    data['time_windows'] = time_windows
    data['num_vehicles'] = num_vehicles
    data['depot'] = depot_index
    data['vehicle_capacities'] = capacities
    
    # Demandas (1 paciente = 1 unidad de capacidad, el depósito demanda 0)
    data['demands'] = [0] + [1] * (num_locations - 1)
    
    return data

def solve_vrp(data, service_time_min, max_work_time_min):
    """Ejecuta el solver de optimización."""
    manager = pywrapcp.RoutingIndexManager(
        len(data['time_matrix']), 
        data['num_vehicles'], 
        data['depot']
    )
    routing = pywrapcp.RoutingModel(manager)

    # --- Dimensión de Tiempo ---
    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # Tiempo de viaje + tiempo de servicio (10 min) en el destino
        travel_time = data['time_matrix'][from_node][to_node]
        if to_node == 0: # Si vuelve al depósito, no hay tiempo de servicio
             return travel_time
        return travel_time + service_time_min

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    routing.AddDimension(
        transit_callback_index,
        30,  # Slack (tiempo de espera permitido si llega antes)
        max_work_time_min,  # Horizonte máximo (8 horas = 480 min)
        False,  # Force start cumul to zero
        'Time'
    )
    time_dimension = routing.GetDimensionOrDie('Time')

    # Restricciones de Ventana Horaria
    for location_idx, (start, end) in enumerate(data['time_windows']):
        if location_idx == 0:
            continue # El depósito no tiene ventana estricta aquí, maneja el total
        index = manager.NodeToIndex(location_idx)
        time_dimension.CumulVar(index).SetRange(start, end)

    # --- Dimensión de Capacidad ---
    def demand_callback(from_index):
        from_node = manager.IndexToNode(from_index)
        return data['demands'][from_node]

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,  # Null capacity slack
        data['vehicle_capacities'],
        True,  # Start cumul to zero
        'Capacity'
    )

    # --- Estrategia de Búsqueda ---
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 5 # Límite de tiempo para resolver

    solution = routing.SolveWithParameters(search_parameters)
    return solution, routing, manager

# ==========================================
# INTERFAZ DE USUARIO (STREAMLIT)
# ==========================================

def main():
    st.title("🚑 Optimización de Rutas de Ambulancias")
    st.markdown("Sistema de gestión de flota con restricciones de ventanas horarias y capacidad.")

    # --- SIDEBAR: Configuración ---
    with st.sidebar:
        st.header("1. Configuración de Flota")
        
        # Configuración de tipos de ambulancia
        fleet_config = []
        col_type, col_cap, col_qty = st.columns(3)
        with col_type:
            st.write("**Tipo**")
            t1 = "Tipo A"
            t2 = "Tipo B"
            t3 = "Tipo C"
            t4 = "UVI"
        with col_cap:
            st.write("**Cap.**")
            c1 = st.number_input("Cap A", value=1, min_value=1, label_visibility="collapsed")
            c2 = st.number_input("Cap B", value=2, min_value=1, label_visibility="collapsed")
            c3 = st.number_input("Cap C", value=4, min_value=1, label_visibility="collapsed")
            c4 = st.number_input("Cap UVI", value=1, min_value=1, label_visibility="collapsed")
        with col_qty:
            st.write("**Cant.**")
            q1 = st.number_input("Cant A", value=2, min_value=0, label_visibility="collapsed")
            q2 = st.number_input("Cant B", value=1, min_value=0, label_visibility="collapsed")
            q3 = st.number_input("Cant C", value=0, min_value=0, label_visibility="collapsed")
            q4 = st.number_input("Cant UVI", value=1, min_value=0, label_visibility="collapsed")

        # Construir lista de vehículos aplanada
        vehicle_capacities = []
        vehicle_names = []
        
        # Agregar según cantidad
        for _ in range(q1): 
            vehicle_capacities.append(c1)
            vehicle_names.append("Tipo A")
        for _ in range(q2): 
            vehicle_capacities.append(c2)
            vehicle_names.append("Tipo B")
        for _ in range(q3): 
            vehicle_capacities.append(c3)
            vehicle_names.append("Tipo C")
        for _ in range(q4): 
            vehicle_capacities.append(c4)
            vehicle_names.append("UVI")

        st.divider()
        st.header("2. Parámetros Operativos")
        depot_address = st.text_input("Dirección Base (Depósito)", "Puerta del Sol, Madrid, España")
        start_hour = st.time_input("Hora Inicio Jornada", value=datetime.strptime("08:00", "%H:%M").time())
        shift_duration = st.slider("Duración Jornada (horas)", 4, 12, 8)
        service_time = st.number_input("Tiempo de Servicio (min/paciente)", value=10)

    # --- MAIN: Carga de Datos ---
    st.header("3. Cargar Pacientes")
    
    uploaded_file = st.file_uploader("Sube tu Excel (.xlsx)", type=['xlsx'])
    
    # Template para descargar
    example_data = {
        'Paciente': ['Juan Pérez', 'Ana Gómez', 'Luis Royo'],
        'Recogida': ['Calle Mayor, Almazán', 'Plaza Mayor, Burgo de Osma', 'Calle Real, Ólvega'],
        'Destino': ['Hospital Santa Bárbara, Soria', 'Centro Salud Almazán', 'Hospital Santa Bárbara, Soria'],
        'Tipo': ['Silla', 'Camilla', 'Sentado'],
        'Hora': ['09:00', '10:30', '11:00']
        }
    st.info("👉 Por favor sube un archivo Excel. Debe tener columnas: 'Paciente', 'Recogida', 'Destino', 'Tipo', 'Hora'.")
    df_template = pd.DataFrame(example_data)
        st.download_button("Descargar Plantilla Ejemplo", 
                           data=df_template.to_csv(index=False).encode('utf-8'),
                           file_name="plantilla_ambulancias.csv",
                           mime='text/csv')
    else:
        try:
            df = pd.read_excel(uploaded_file)
            st.success("Archivo cargado correctamente.")
            st.dataframe(df.head())
            
            # Validar columnas
            required_cols = ['Paciente', 'Recogida', 'Destino', 'Tipo']
            if not all(col in df.columns for col in required_cols):
                st.error(f"Faltan columnas requeridas: {required_cols}")
                st.stop()
                
            if st.button("🚀 Optimizar Rutas"):
                
                with st.status("Procesando...", expanded=True) as status:
                    
                    # 1. Geocodificación
                    status.write("📍 Geocodificando direcciones (esto puede tardar unos segundos)...")
                    locations = []
                    # El índice 0 es el depósito
                    depot_coords = geocode_address(depot_address)
                    if not depot_coords:
                        st.error("No se pudo localizar el depósito.")
                        st.stop()
                    
                    locations.append(depot_coords)
                    valid_patients = []
                    
                    progress_bar = st.progress(0)
                    
                    for idx, row in df.iterrows():
                        coords = geocode_address(row['Direccion'])
                        if coords:
                            locations.append(coords)
                            valid_patients.append(row)
                        else:
                            st.warning(f"No se pudo localizar: {row['Direccion']}")
                        progress_bar.progress((idx + 1) / len(df))
                    
                    if len(locations) < 2:
                        st.error("No hay suficientes destinos válidos para optimizar.")
                        st.stop()

                    # 2. Preparar Ventanas de Tiempo (convertir HH:MM a minutos desde inicio jornada)
                    # El depósito siempre está abierto (0 a max jornada)
                    time_windows = [(0, shift_duration * 60)] 
                    
                    start_minutes_base = start_hour.hour * 60 + start_hour.minute
                    
                    for p in valid_patients:
                        try:
                            t_min = datetime.strptime(str(p['Hora_Min']), "%H:%M:%S") if len(str(p['Hora_Min'])) > 5 else datetime.strptime(str(p['Hora_Min']), "%H:%M")
                            t_max = datetime.strptime(str(p['Hora_Max']), "%H:%M:%S") if len(str(p['Hora_Max'])) > 5 else datetime.strptime(str(p['Hora_Max']), "%H:%M")
                            
                            m_min = t_min.hour * 60 + t_min.minute - start_minutes_base
                            m_max = t_max.hour * 60 + t_max.minute - start_minutes_base
                            
                            # Normalizar si es antes de la hora de inicio (ej. citas día siguiente o error)
                            if m_min < 0: m_min = 0
                            if m_max < 0: m_max = shift_duration * 60
                            
                            time_windows.append((int(m_min), int(m_max)))
                        except Exception as e:
                            # Si falla el parseo, ventana amplia
                            time_windows.append((0, shift_duration * 60))

                    # 3. Resolver
                    status.write("🧮 Calculando matriz de distancias y optimizando...")
                    
                    data = create_data_model(
                        locations, 
                        vehicle_capacities, 
                        time_windows, 
                        len(vehicle_capacities)
                    )
                    
                    solution, routing, manager = solve_vrp(data, service_time, shift_duration * 60)
                    
                    status.update(label="¡Optimización completada!", state="complete", expanded=False)

                # --- Resultados ---
                if solution:
                    st.header("4. Hoja de Ruta Generada")
                    
                    route_data = []
                    time_dim = routing.GetDimensionOrDie('Time')
                    
                    for vehicle_id in range(data['num_vehicles']):
                        index = routing.Start(vehicle_id)
                        route_name = f"Vehículo {vehicle_id + 1} ({vehicle_names[vehicle_id]})"
                        
                        # Comprobar si el vehículo se usa (si va directo al final, no se usa)
                        if routing.IsEnd(solution.Value(routing.NextVar(index))):
                            continue
                            
                        stop_num = 1
                        while not routing.IsEnd(index):
                            node_index = manager.IndexToNode(index)
                            time_var = time_dim.CumulVar(index)
                            arrival_min = solution.Min(time_var)
                            
                            # Calcular hora real
                            real_arrival_time = (datetime.combine(datetime.today(), start_hour) + timedelta(minutes=arrival_min)).strftime("%H:%M")
                            
                            # Datos del lugar
                            if node_index == 0:
                                loc_name = "DEPÓSITO (Salida)"
                                address = depot_address
                                patient_name = "-"
                            else:
                                # -1 porque valid_patients no tiene el depósito
                                pat = valid_patients[node_index - 1] 
                                loc_name = f"Parada {stop_num}"
                                address = pat['Direccion']
                                patient_name = pat['Paciente']
                                stop_num += 1
                            
                            route_data.append({
                                "Vehículo": route_name,
                                "Orden": stop_num if node_index !=0 else 0,
                                "Tipo Lugar": "Base" if node_index == 0 else "Paciente",
                                "Nombre": patient_name,
                                "Dirección": address,
                                "Hora Estimada Llegada": real_arrival_time,
                                "Minutos Acumulados": arrival_min
                            })
                            
                            index = solution.Value(routing.NextVar(index))
                        
                        # Añadir retorno al depósito
                        node_index = manager.IndexToNode(index)
                        time_var = time_dim.CumulVar(index)
                        arrival_min = solution.Min(time_var)
                        real_arrival_time = (datetime.combine(datetime.today(), start_hour) + timedelta(minutes=arrival_min)).strftime("%H:%M")
                        
                        route_data.append({
                            "Vehículo": route_name,
                            "Orden": stop_num,
                            "Tipo Lugar": "DEPÓSITO (Fin)",
                            "Nombre": "-",
                            "Dirección": depot_address,
                            "Hora Estimada Llegada": real_arrival_time,
                            "Minutos Acumulados": arrival_min
                        })

                    # Visualización
                    df_results = pd.DataFrame(route_data)
                    st.dataframe(df_results)
                    
                    # Mapa simple de rutas
                    st.map(pd.DataFrame(locations, columns=['lat', 'lon']))

                    # Exportar CSV
                    csv = df_results.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Descargar Hoja de Ruta (CSV)",
                        csv,
                        "hoja_de_ruta.csv",
                        "text/csv",
                        key='download-csv'
                    )
                    
                else:
                    st.error("No se encontró solución factible. Intenta aumentar la flota o relajar las ventanas horarias.")

        except Exception as e:
            st.error(f"Ocurrió un error al procesar el archivo: {e}")

if __name__ == "__main__":
    main()





