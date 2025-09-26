import streamlit as st
import pandas as pd
import numpy as np
import pickle
import json
import matplotlib.pyplot as plt
import seaborn as sns
from math import pi
import plotly.graph_objects as go
import plotly.express as px
import folium
from folium import plugins
from streamlit_folium import st_folium
import requests
import io

# Configure the page
st.set_page_config(
    page_title="Asteroid Impact Simulator",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .impact-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .hazardous {
        background-color: #ffcccc;
    }
    .safe {
        background-color: #ccffcc;
    }
    .map-container {
        border: 2px solid #1f77b4;
        border-radius: 10px;
        padding: 10px;
        margin: 10px 0;
    }
    .zone-legend {
        background: white;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #ccc;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def load_models():
    """Load trained models and metadata"""
    try:
        with open("asteroid_models.pkl", "rb") as f:
            models_data = pickle.load(f)

        with open("model_features.json", "r") as f:
            feature_info = json.load(f)

        return models_data['models'], models_data['scalers'], feature_info, models_data.get('metadata', {})
    except FileNotFoundError:
        st.error("❌ Model files not found. Please run main.py first to train the models.")
        st.stop()


def predict_impact_consequences(diameter, velocity, mass, miss_distance):
    """Predict various impact consequences with correct feature mapping"""
    models, scalers, feature_info, metadata = load_models()

    try:
        # Calculate absolute magnitude (used in some models)
        absolute_magnitude = 20 - 2.5 * np.log10(diameter) if diameter > 0 else 20

        # Prepare input data for different models with correct feature counts
        input_energy = np.array([[diameter, velocity, mass, absolute_magnitude]])
        input_hazard = np.array([[diameter, velocity, mass, absolute_magnitude, miss_distance]])
        input_impact = np.array([[diameter, velocity, miss_distance]])

        # Scale features appropriately
        energy_scaled = scalers['energy_scaler'].transform(input_energy)
        impact_scaled = scalers['impact_scaler'].transform(input_impact)

        # Make predictions
        energy_pred_log = models['energy_predictor'].predict(energy_scaled)[0]
        energy_pred = np.expm1(energy_pred_log)

        hazard_prob = models['hazard_predictor'].predict(input_hazard)[0]

        impact_energy_log = models['impact_predictor'].predict(impact_scaled)[0]
        impact_energy = np.expm1(impact_energy_log)

        return {
            'kinetic_energy_joules': energy_pred,
            'impact_energy_megatons': impact_energy,
            'hazard_probability': max(0, min(1, hazard_prob)),
            'is_hazardous': hazard_prob > 0.5
        }

    except Exception as e:
        st.error(f"❌ Prediction error: {e}")
        return {
            'kinetic_energy_joules': 0,
            'impact_energy_megatons': 0,
            'hazard_probability': 0,
            'is_hazardous': False
        }


def calculate_impact_effects(impact_energy_megatons, diameter, velocity, terrain_type, impact_angle):
    """Calculate various impact effects based on energy and size"""
    effects = {}

    try:
        angle_rad = np.radians(impact_angle)

        # Crater size estimation
        effects['crater_diameter'] = 1.2 * diameter * (impact_energy_megatons ** 0.3) * np.sin(angle_rad)
        effects['crater_depth'] = 0.25 * effects['crater_diameter']

        # Seismic effects
        effects['earthquake_magnitude'] = 0.67 * np.log10(impact_energy_megatons * 4.184e15) - 5.87

        # Effect radii in meters
        effects['fireball_radius'] = 20 * (impact_energy_megatons ** 0.4) * 1000  # Convert to meters
        effects['blast_radius_5psi'] = 100 * (impact_energy_megatons ** 0.33) * 1000
        effects['thermal_radius'] = 50 * (impact_energy_megatons ** 0.4) * 1000
        effects['ejecta_radius'] = 200 * (impact_energy_megatons ** 0.3) * 1000

        # Regional effects (larger scale)
        effects['regional_blast_radius'] = effects['blast_radius_5psi'] * 5
        effects['seismic_effect_radius'] = effects['blast_radius_5psi'] * 10

        if terrain_type == "Ocean" and diameter > 100:
            effects['tsunami_wave_height'] = 0.5 * (impact_energy_megatons ** 0.5)
            effects['tsunami_reach'] = 1000 * (impact_energy_megatons ** 0.25) * 1000
        else:
            effects['tsunami_wave_height'] = 0
            effects['tsunami_reach'] = 0

    except Exception as e:
        st.error(f"❌ Error calculating impact effects: {e}")
        effects = {
            'crater_diameter': 0, 'earthquake_magnitude': 0, 'fireball_radius': 0,
            'blast_radius_5psi': 0, 'thermal_radius': 0, 'ejecta_radius': 0,
            'regional_blast_radius': 0, 'seismic_effect_radius': 0
        }

    return effects


def create_impact_map(lat, lon, consequences, effects, terrain_type):
    """Create an interactive Folium map showing impact zones"""

    try:
        # Create base map with proper attribution
        m = folium.Map(
            location=[lat, lon],
            zoom_start=8,
            tiles='OpenStreetMap',
            control_scale=True  # This adds a scale to the map
        )

        # Add tile layers with proper attribution
        folium.TileLayer(
            tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
            attr='Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
            name='OpenTopoMap'
        ).add_to(m)

        folium.TileLayer(
            tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            name='CartoDB Dark'
        ).add_to(m)

        # Impact point marker
        folium.Marker(
            [lat, lon],
            popup=f"""
            <b>Impact Point - Ground Zero</b><br>
            <b>Energy:</b> {consequences['impact_energy_megatons']:.1f} Megatons<br>
            <b>Crater Diameter:</b> {effects.get('crater_diameter', 0) / 1000:.1f} km<br>
            <b>Earthquake:</b> Magnitude {effects.get('earthquake_magnitude', 0):.1f}
            """,
            tooltip="Ground Zero - Impact Point",
            icon=folium.Icon(color='red', icon='warning', prefix='fa')
        ).add_to(m)

        # Define impact zones with colors and labels
        zones = [
            {'name': 'Fireball Zone', 'radius': effects.get('fireball_radius', 0), 'color': 'red', 'fill': True},
            {'name': 'Total Destruction', 'radius': effects.get('blast_radius_5psi', 0), 'color': 'darkred',
             'fill': True},
            {'name': 'Thermal Radiation', 'radius': effects.get('thermal_radius', 0), 'color': 'orange', 'fill': False},
            {'name': 'Ejecta Zone', 'radius': effects.get('ejecta_radius', 0), 'color': 'yellow', 'fill': False},
            {'name': 'Regional Effects', 'radius': effects.get('regional_blast_radius', 0), 'color': 'lightgray',
             'fill': False}
        ]

        # Add zones to map
        for zone in zones:
            if zone['radius'] > 0:
                folium.Circle(
                    location=[lat, lon],
                    radius=zone['radius'],
                    popup=f"""
                    <b>{zone['name']}</b><br>
                    Radius: {zone['radius'] / 1000:.1f} km<br>
                    Area: {np.pi * (zone['radius'] / 1000) ** 2:,.0f} km²
                    """,
                    tooltip=zone['name'],
                    color=zone['color'],
                    fill=zone['fill'],
                    fillOpacity=0.2 if zone['fill'] else 0,
                    weight=3
                ).add_to(m)

        # Add tsunami zone if applicable
        if terrain_type == "Ocean" and effects.get('tsunami_reach', 0) > 0:
            folium.Circle(
                location=[lat, lon],
                radius=effects['tsunami_reach'],
                popup=f"""
                <b>Tsunami Effect Zone</b><br>
                Radius: {effects['tsunami_reach'] / 1000:.1f} km<br>
                Wave Height: {effects.get('tsunami_wave_height', 0):.1f} m
                """,
                tooltip="Tsunami Zone",
                color='blue',
                fill=False,
                weight=3,
                dash_array='5, 5'
            ).add_to(m)

        # Add major cities within affected area for reference
        major_cities = [
            {"name": "New York", "lat": 40.7128, "lon": -74.0060},
            {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
            {"name": "Chicago", "lat": 41.8781, "lon": -87.6298},
            {"name": "Miami", "lat": 25.7617, "lon": -80.1918},
            {"name": "Seattle", "lat": 47.6062, "lon": -122.3321},
        ]

        for city in major_cities:
            # Calculate distance from impact
            distance = np.sqrt((city['lat'] - lat) ** 2 + (city['lon'] - lon) ** 2) * 111  # approx km per degree
            if distance < 2000:  # Only show cities within 2000 km
                folium.Marker(
                    [city['lat'], city['lon']],
                    popup=f"{city['name']}<br>Distance: {distance:.0f} km",
                    tooltip=city['name'],
                    icon=folium.Icon(color='blue', icon='city', prefix='fa')
                ).add_to(m)

        # Add measurement tool
        plugins.MeasureControl(
            position='bottomleft',
            primary_length_unit='kilometers',
            secondary_length_unit='miles'
        ).add_to(m)

        # Add fullscreen control
        plugins.Fullscreen().add_to(m)

        # Add minimap
        plugins.MiniMap().add_to(m)

        # Add layer control
        folium.LayerControl().add_to(m)

        return m

    except Exception as e:
        st.error(f"❌ Error in map creation: {e}")
        # Return a simple map as fallback
        m = folium.Map(location=[lat, lon], zoom_start=8, control_scale=True)
        folium.Marker([lat, lon], popup="Impact Point").add_to(m)
        return m


def get_population_data(lat, lon, radius_km):
    """Estimate population in affected area"""
    # Simplified population density model
    base_population_density = {
        'Urban': 2000,  # people per km²
        'Suburban': 500,
        'Rural': 50,
        'Desert': 5,
        'Ocean': 0
    }

    area_km2 = np.pi * (radius_km ** 2)

    # Estimate density based on latitude and typical population patterns
    if -30 < lat < 30:  # Tropical regions - higher density near coasts
        density = base_population_density['Urban'] * 1.5
    elif 30 < lat < 50 or -50 < lat < -30:  # Temperate regions - moderate density
        density = base_population_density['Suburban']
    else:  # High latitudes - lower density
        density = base_population_density['Rural']

    estimated_population = int(area_km2 * density)
    return estimated_population


def create_impact_report(lat, lon, consequences, effects, terrain_type):
    """Generate a comprehensive impact assessment report"""

    # Calculate affected area and population
    main_blast_radius_km = effects.get('blast_radius_5psi', 0) / 1000
    regional_radius_km = effects.get('regional_blast_radius', 0) / 1000

    main_population = get_population_data(lat, lon, main_blast_radius_km)
    regional_population = get_population_data(lat, lon, regional_radius_km)

    report = {
        'impact_energy': consequences['impact_energy_megatons'],
        'earthquake_magnitude': effects.get('earthquake_magnitude', 0),
        'crater_diameter_km': effects.get('crater_diameter', 0) / 1000,
        'main_blast_radius_km': main_blast_radius_km,
        'regional_effect_radius_km': regional_radius_km,
        'estimated_casualties': main_population,
        'regional_affected_population': regional_population - main_population,
        'tsunami_risk': 'High' if terrain_type == "Ocean" and consequences['impact_energy_megatons'] > 1 else 'Low',
        'global_effects': 'Significant' if consequences['impact_energy_megatons'] > 1000 else 'Minimal'
    }

    return report


def main():
    st.markdown('<div class="main-header">🌍 Asteroid Impact Simulator</div>', unsafe_allow_html=True)

    # Sidebar for user inputs
    st.sidebar.header("⚙️ Simulation Parameters")

    # Asteroid characteristics
    st.sidebar.subheader("Asteroid Properties")
    diameter = st.sidebar.slider("Diameter (meters)", 1.0, 5000.0, 100.0)
    velocity = st.sidebar.slider("Velocity (m/s)", 1000.0, 100000.0, 20000.0)
    density = st.sidebar.slider("Density (kg/m³)", 1000.0, 5000.0, 2000.0)
    miss_distance_km = st.sidebar.slider("Miss Distance (km)", 0.0, 1000000.0, 10000.0)

    # Impact scenario
    st.sidebar.subheader("Impact Scenario")
    impact_angle = st.sidebar.slider("Impact Angle (degrees)", 0.0, 90.0, 45.0)
    terrain_type = st.sidebar.selectbox("Impact Terrain", ["Ocean", "Land", "Urban", "Desert", "Ice"])

    # Geographical location
    st.sidebar.subheader("🌍 Impact Location")
    st.sidebar.write("Click on the map below to set impact location")

    # Default location (can be set by map click)
    if 'impact_location' not in st.session_state:
        st.session_state.impact_location = [40.7128, -74.0060]  # New York default

    # Small map for location selection in sidebar
    col1, col2 = st.sidebar.columns(2)
    with col1:
        lat = st.sidebar.number_input("Latitude", -90.0, 90.0, st.session_state.impact_location[0], format="%.4f")
    with col2:
        lon = st.sidebar.number_input("Longitude", -180.0, 180.0, st.session_state.impact_location[1], format="%.4f")

    # Calculate mass
    mass = density * (4 / 3) * np.pi * ((diameter / 2) ** 3)
    miss_distance = miss_distance_km * 1000

    # Main content area with tabs
    tab1, tab2, tab3 = st.tabs(["📊 Impact Analysis", "🗺️ Geographical Impact", "📈 Simulation Results"])

    with tab1:
        st.subheader("🚀 Impact Prediction Results")

        if st.button("Run Impact Simulation", type="primary", key="run_simulation"):
            with st.spinner("Calculating impact consequences..."):
                try:
                    # Predict consequences
                    consequences = predict_impact_consequences(
                        diameter, velocity, mass, miss_distance
                    )

                    # Calculate additional effects
                    consequences['effects'] = calculate_impact_effects(
                        consequences['impact_energy_megatons'],
                        diameter, velocity, terrain_type, impact_angle
                    )

                    # Store results in session state for other tabs
                    st.session_state.consequences = consequences
                    st.session_state.impact_params = {
                        'lat': lat, 'lon': lon, 'terrain_type': terrain_type,
                        'diameter': diameter, 'velocity': velocity
                    }

                    # Display results
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("Kinetic Energy", f"{consequences['kinetic_energy_joules']:.2e} J")
                        st.metric("Equivalent Megatons", f"{consequences['impact_energy_megatons']:.1f} MT")
                        st.metric("Crater Diameter", f"{consequences['effects']['crater_diameter'] / 1000:.1f} km")

                    with col2:
                        st.metric("Hazard Probability", f"{consequences['hazard_probability'] * 100:.1f}%")
                        st.metric("Earthquake Magnitude", f"{consequences['effects']['earthquake_magnitude']:.1f}")
                        st.metric("Blast Radius", f"{consequences['effects']['blast_radius_5psi'] / 1000:.1f} km")

                    with col3:
                        st.metric("Fireball Radius", f"{consequences['effects']['fireball_radius'] / 1000:.1f} km")
                        st.metric("Thermal Radius", f"{consequences['effects']['thermal_radius'] / 1000:.1f} km")
                        if terrain_type == "Ocean":
                            st.metric("Tsunami Height",
                                      f"{consequences['effects'].get('tsunami_wave_height', 0):.1f} m")

                    # Hazard warning
                    if consequences['is_hazardous']:
                        st.error("🚨 HIGH IMPACT HAZARD - Significant damage expected!")
                    else:
                        st.success("✅ LOW IMPACT RISK - Minimal damage expected")

                except Exception as e:
                    st.error(f"❌ Error running simulation: {e}")

    with tab2:
        st.subheader("🗺️ Geographical Impact Visualization")

        if 'consequences' in st.session_state:
            consequences = st.session_state.consequences
            params = st.session_state.impact_params

            # Create the impact map
            st.markdown('<div class="map-container">', unsafe_allow_html=True)

            try:
                impact_map = create_impact_map(
                    params['lat'], params['lon'],
                    consequences, consequences['effects'],
                    params['terrain_type']
                )

                # Display the map
                st_data = st_folium(impact_map, width=800, height=600)

                # Update location if user clicks on map
                if st_data and st_data.get('last_clicked'):
                    st.session_state.impact_location = [
                        st_data['last_clicked']['lat'],
                        st_data['last_clicked']['lng']
                    ]
                    st.rerun()

            except Exception as e:
                st.error(f"❌ Error creating map: {e}")
                # Fallback simple map
                m = folium.Map(location=[params['lat'], params['lon']], zoom_start=8, control_scale=True)
                folium.Marker([params['lat'], params['lon']], popup="Impact Point").add_to(m)
                st_folium(m, width=800, height=400)

            st.markdown('</div>', unsafe_allow_html=True)

            # Zone legend
            st.subheader("Impact Zone Legend")
            legend_cols = st.columns(5)
            zones_info = [
                ("🔥 Fireball Zone", "red", "Complete vaporization"),
                ("💥 Total Destruction", "darkred", "100% fatality rate"),
                ("☀️ Thermal Radiation", "orange", "3rd degree burns"),
                ("🌋 Ejecta Zone", "yellow", "Debris fallout"),
                ("🌍 Regional Effects", "lightgray", "Structural damage")
            ]

            for i, (name, color, desc) in enumerate(zones_info):
                with legend_cols[i]:
                    st.markdown(f"""
                    <div style='background-color: {color}; padding: 10px; border-radius: 5px; text-align: center;'>
                    <strong>{name}</strong><br>
                    <small>{desc}</small>
                    </div>
                    """, unsafe_allow_html=True)

            # Impact assessment report
            st.subheader("📋 Impact Assessment Report")
            report = create_impact_report(
                params['lat'], params['lon'],
                consequences, consequences['effects'],
                params['terrain_type']
            )

            report_cols = st.columns(2)
            with report_cols[0]:
                st.info(f"""
                **Immediate Effects:**
                - Impact Energy: {report['impact_energy']:.1f} Megatons
                - Earthquake Magnitude: {report['earthquake_magnitude']:.1f}
                - Crater Diameter: {report['crater_diameter_km']:.1f} km
                - Blast Radius: {report['main_blast_radius_km']:.1f} km
                """)

            with report_cols[1]:
                st.warning(f"""
                **Human Impact:**
                - Immediate Casualties: {report['estimated_casualties']:,}
                - Regional Affected: {report['regional_affected_population']:,}
                - Tsunami Risk: {report['tsunami_risk']}
                - Global Effects: {report['global_effects']}
                """)

        else:
            st.info("👆 Run the impact simulation first to see geographical effects")

    with tab3:
        st.subheader("📈 Simulation Results and Analysis")

        if 'consequences' in st.session_state:
            consequences = st.session_state.consequences

            # Historical comparison chart
            st.subheader("📊 Historical Impact Comparison")
            comparisons = {
                "Tunguska Event (1908)": 10,
                "Chelyabinsk (2013)": 0.5,
                "Hiroshima Bomb": 0.015,
                "Chicxulub (Dinosaur)": 100000000
            }

            comp_fig = go.Figure()
            comp_fig.add_bar(
                x=list(comparisons.keys()),
                y=list(comparisons.values()),
                name="Historical Events",
                marker_color='lightblue'
            )
            comp_fig.add_scatter(
                x=["Current Simulation"],
                y=[consequences['impact_energy_megatons']],
                mode='markers',
                name="Your Simulation",
                marker=dict(size=15, color='red', symbol='diamond')
            )

            comp_fig.update_layout(
                yaxis_type="log",
                title="Energy Comparison (Megatons of TNT)",
                yaxis_title="Energy (Megatons)",
                showlegend=True,
                height=400
            )
            st.plotly_chart(comp_fig, use_container_width=True)

            # Mitigation strategies
            st.subheader("🛡️ Mitigation Strategies")
            strategies = []

            if diameter < 50:
                strategies.extend([
                    "**Kinetic Impactor**: Small spacecraft collision to alter trajectory",
                    "**Gravity Tractor**: Use spacecraft's gravity for gradual deflection",
                    "**Laser Ablation**: Surface vaporization for momentum change"
                ])
            elif diameter < 200:
                strategies.extend([
                    "**Nuclear Explosive**: Subsurface detonation for maximum deflection",
                    "**Enhanced Gravity Tractor**: Multiple spacecraft coordination",
                    "**Mass Driver**: Install propulsion system on asteroid"
                ])
            else:
                strategies.extend([
                    "**Combined Approach**: Multiple deflection methods required",
                    "**Early Detection**: Decades of advance warning needed",
                    "**Civil Defense**: Focus on evacuation and infrastructure protection"
                ])

            for strategy in strategies:
                st.write(f"• {strategy}")

            # Risk assessment
            st.subheader("📉 Risk Assessment")
            risk_level = "EXTREME" if consequences['impact_energy_megatons'] > 1000 else \
                "HIGH" if consequences['impact_energy_megatons'] > 100 else \
                    "MODERATE" if consequences['impact_energy_megatons'] > 10 else "LOW"

            risk_color = {
                "EXTREME": "red",
                "HIGH": "orange",
                "MODERATE": "yellow",
                "LOW": "green"
            }

            st.markdown(f"""
            <div style='background-color: {risk_color[risk_level]}; padding: 20px; border-radius: 10px; text-align: center;'>
            <h2 style='color: white; margin: 0;'>RISK LEVEL: {risk_level}</h2>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.info("👆 Run the simulation first to see detailed results")

    # Educational sidebar
    st.sidebar.subheader("🎓 Educational Information")
    st.sidebar.info(f"""
    **Current Simulation:**
    - Diameter: {diameter} m
    - Velocity: {velocity:,.0f} m/s
    - Mass: {mass:.2e} kg
    - Impact Location: {lat:.4f}, {lon:.4f}
    """)


if __name__ == "__main__":
    main()