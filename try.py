import streamlit as st
import pandas as pd
import folium
import math
import numpy as np
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
from geopy.distance import geodesic
import altair as alt
from PIL import Image
import io
import base64

# Government standards (expand as needed)
GOVERNMENT_STANDARDS = {
    "schools": {
        "ratio": 0.00107,  # 1 school per 933 people
        "unit": "per person",
        "service_radius_km": 5.0,
        "icon": "book",
        "color": "blue"
    },
    "hospitals": {
        "ratio": 0.0000184,  # 1 hospital per 54,300 people
        "unit": "per person",
        "service_radius_km": 20.0,
        "icon": "plus-circle",
        "color": "red"
    },
    "police_stations": {
        "ratio": 0.0000111,  # 1 station per 89,800 people
        "unit": "per person",
        "service_radius_km": 15.0,
        "icon": "shield-alt",
        "color": "darkblue"
    },
    "parks": {
        "ratio": 0.0001,  # 1 park per 10,000 people
        "unit": "per 1000 people",
        "area_standard": 10,  # sqm per person
        "service_radius_km": 2.0,
        "icon": "tree",
        "color": "green"
    },
    "pharmacies": {
        "ratio": 0.000606,  # 1 pharmacy per 1,650 people
        "unit": "per person",
        "service_radius_km": 3.0,
        "icon": "pills",
        "color": "lightred"
    }
}

def clean_coordinate(coord):
    """Handle various coordinate formats including °N/°E notations"""
    if pd.isna(coord):
        return None
    if isinstance(coord, str):
        coord = coord.replace('°N', '').replace('°E', '').replace('°', '').strip()
        if ' ' in coord:
            coord = coord.split()[0]  # Take first part if multiple values
    try:
        return float(coord)
    except (ValueError, TypeError):
        return None

def standardize_facility_data(df, facility_type):
    """Standardize different facility datasets to common format"""
    standardized = pd.DataFrame()
    
    # Common renamings
    column_map = {
        'Name': 'name',
        'Name of Facility': 'name',
        'Name of Police Station': 'name',
        'Name of facility': 'name',
        'Latitude': 'latitude',
        'Location_latitude': 'latitude',
        'Longitude': 'longitude',
        'Location_longitude': 'longitude',
        'Area (in square meters)': 'area_sqm'
    }
    
    df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
    
    # Handle specific cases
    if facility_type == "parks":
        if 'Type of facility- public park/ public garden/ public open space' in df.columns:
            df['type'] = df['Type of facility- public park/ public garden/ public open space']
    
    # Clean coordinates
    df['latitude'] = df['latitude'].apply(clean_coordinate)
    df['longitude'] = df['longitude'].apply(clean_coordinate)
    
    # Drop rows with invalid coordinates
    df = df.dropna(subset=['latitude', 'longitude'])
    
    return df

def calculate_requirements(population, facility_type):
    """Calculate required facilities for given population"""
    standard = GOVERNMENT_STANDARDS.get(facility_type, {})
    ratio = standard.get("ratio", 0)
    return math.ceil(population * ratio)

def calculate_service_coverage(facilities, center_point, radius_km):
    """Calculate what percentage of area is covered by facilities"""
    if len(facilities) == 0:
        return 0.0
    
    covered = 0
    for _, facility in facilities.iterrows():
        dist = geodesic(
            (center_point[0], center_point[1]),
            (facility['latitude'], facility['longitude'])
        ).km
        if dist <= radius_km:
            covered += 1
    
    return (covered / len(facilities)) * 100

def create_facility_map(facilities, facility_type, center_coords):
    """Create Folium map showing facility locations and service areas"""
    standard = GOVERNMENT_STANDARDS.get(facility_type, {})
    m = folium.Map(location=center_coords, zoom_start=12)
    
    # Add service radius circles
    if "service_radius_km" in standard:
        for _, row in facilities.iterrows():
            folium.Circle(
                location=[row['latitude'], row['longitude']],
                radius=standard["service_radius_km"] * 1000,  # Convert km to meters
                color=standard.get("color", "blue"),
                fill=True,
                fill_opacity=0.2,
                popup=f"Service area: {standard['service_radius_km']} km"
            ).add_to(m)
    
    # Add facility markers with clustering
    marker_cluster = MarkerCluster().add_to(m)
    for _, row in facilities.iterrows():
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=f"{facility_type.title()}: {row.get('name', 'Unnamed')}",
            icon=folium.Icon(
                icon=standard.get("icon", "info-sign"),
                color=standard.get("color", "blue")
            )
        ).add_to(marker_cluster)
    
    return m

def create_gap_chart(gap_data):
    """Create Altair chart visualizing gaps"""
    source = pd.DataFrame({
        'Metric': ['Actual', 'Required', 'Gap'],
        'Count': [gap_data['actual'], gap_data['required'], gap_data['gap']]
    })
    
    chart = alt.Chart(source).mark_bar().encode(
        x='Metric',
        y='Count',
        color=alt.Color('Metric', scale=alt.Scale(
            domain=['Actual', 'Required', 'Gap'],
            range=['#4c78a8', '#72b7b2', '#e45756']
        )),
        tooltip=['Metric', 'Count']
    ).properties(
        width=600,
        height=400,
        title=f"Amenity Gap Analysis"
    )
    
    return chart

def analyze_amenities(population, facilities, facility_type):
    """Comprehensive analysis of amenity gaps"""
    standard = GOVERNMENT_STANDARDS.get(facility_type, {})
    
    # Basic count analysis
    actual_count = len(facilities)
    required_count = calculate_requirements(population, facility_type)
    gap = max(0, required_count - actual_count)
    
    # Service coverage analysis
    if len(facilities) > 0:
        center_point = [facilities['latitude'].mean(), facilities['longitude'].mean()]
        coverage_radius = standard.get("service_radius_km", 5.0)
        coverage_pct = calculate_service_coverage(facilities, center_point, coverage_radius)
    else:
        coverage_pct = 0.0
    
    # Area analysis for parks
    area_gap = 0
    if facility_type == "parks" and "area_sqm" in facilities.columns:
        total_area = facilities['area_sqm'].sum()
        required_area = population * standard.get("area_standard", 0)
        area_gap = max(0, required_area - total_area)
    
    return {
        "actual": actual_count,
        "required": required_count,
        "gap": gap,
        "sufficient": actual_count >= required_count,
        "coverage_pct": coverage_pct,
        "area_gap": area_gap,
        "total_area": total_area if facility_type == "parks" else None,
        "required_area": required_area if facility_type == "parks" else None
    }

def get_map_download_link(map_obj, facility_type):
    """Generate download link for the map"""
    map_obj.save(f"{facility_type}_map.html")
    with open(f"{facility_type}_map.html", "rb") as f:
        html = f.read()
    b64 = base64.b64encode(html).decode()
    href = f'<a href="data:file/html;base64,{b64}" download="{facility_type}_map.html">Download Map as HTML</a>'
    return href

def main():
    st.set_page_config(
        page_title="Rural Amenity Gap Analyzer",
        page_icon="🏘️",
        layout="wide"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
    .metric-box {
        padding: 15px;
        border-radius: 10px;
        background-color: #f0f2f6;
        margin-bottom: 20px;
    }
    .sufficient {
        border-left: 5px solid #2ecc71;
    }
    .deficient {
        border-left: 5px solid #e74c3c;
    }
    .report-title {
        color: #3498db;
        border-bottom: 2px solid #3498db;
        padding-bottom: 5px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🏘️ Rural Amenity Gap Analyzer")
    st.markdown("""
    This tool analyzes gaps in rural amenities compared to government standards, 
    providing spatial visualization of facility distribution and service coverage.
    """)
    
    # Sidebar controls
    with st.sidebar:
        st.header("Analysis Parameters")
        population = st.number_input(
            "Population served:",
            min_value=100,
            value=10000,
            step=100
        )
        
        facility_type = st.selectbox(
            "Amenity type:",
            list(GOVERNMENT_STANDARDS.keys()),
            format_func=lambda x: x.title()
        )
        
        uploaded_file = st.file_uploader(
            f"Upload {facility_type} data (CSV):",
            type="csv"
        )
        
        st.markdown("---")
        st.markdown("**Government Standards:**")
        standard = GOVERNMENT_STANDARDS[facility_type]
        st.write(f"- Ratio: 1 {facility_type[:-1]} per {int(1/standard['ratio']):,} people")
        if "service_radius_km" in standard:
            st.write(f"- Service radius: {standard['service_radius_km']} km")
        if "area_standard" in standard:
            st.write(f"- Area standard: {standard['area_standard']} sqm per person")
    
    if uploaded_file:
        try:
            # Load and standardize data
            df = pd.read_csv(uploaded_file)
            facilities = standardize_facility_data(df, facility_type)
            
            if len(facilities) == 0:
                st.warning("No valid facility locations found in the uploaded file.")
                return
            
            # Perform analysis
            analysis = analyze_amenities(population, facilities, facility_type)
            center_coords = [facilities['latitude'].mean(), facilities['longitude'].mean()]
            
            # Display results
            st.header("📊 Gap Analysis Results")
            
            # Metrics row
            col1, col2, col3, col4 = st.columns(4)
            status_class = "sufficient" if analysis["sufficient"] else "deficient"
            
            with col1:
                st.markdown(
                    f"<div class='metric-box {status_class}'>"
                    f"<h3>Actual</h3>"
                    f"<h2>{analysis['actual']}</h2>"
                    f"<p>facilities present</p>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            
            with col2:
                st.markdown(
                    f"<div class='metric-box'>"
                    f"<h3>Required</h3>"
                    f"<h2>{analysis['required']}</h2>"
                    f"<p>facilities needed</p>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            
            with col3:
                st.markdown(
                    f"<div class='metric-box'>"
                    f"<h3>Gap</h3>"
                    f"<h2>{analysis['gap']}</h2>"
                    f"<p>additional needed</p>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            
            with col4:
                coverage_color = "#2ecc71" if analysis["coverage_pct"] > 75 else "#e74c3c"
                st.markdown(
                    f"<div class='metric-box'>"
                    f"<h3>Service Coverage</h3>"
                    f"<h2 style='color: {coverage_color}'>{analysis['coverage_pct']:.1f}%</h2>"
                    f"<p>within service radius</p>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            
            # Visualizations
            st.header("📈 Visualizations")
            
            tab1, tab2 = st.tabs(["Map View", "Data Charts"])
            
            with tab1:
                # Create and display map
                map_obj = create_facility_map(facilities, facility_type, center_coords)
                st_data = st_folium(map_obj, width=1200, height=600)
                
                # Download link for map
                st.markdown(get_map_download_link(map_obj, facility_type), unsafe_allow_html=True)
            
            with tab2:
                # Gap chart
                st.altair_chart(create_gap_chart(analysis), use_container_width=True)
                
                # Facilities table
                st.subheader("Facility Details")
                st.dataframe(facilities.head(100))
            
            # Detailed report
            st.header("📝 Detailed Report")
            
            if analysis["sufficient"]:
                st.success(f"✅ This area has sufficient {facility_type.replace('_', ' ')} "
                         f"according to government standards.")
            else:
                st.error(f"⚠️ This area is deficient by {analysis['gap']} {facility_type.replace('_', ' ')}. "
                       f"Recommend adding {analysis['gap']} more facilities.")
            
            if analysis["coverage_pct"] < 75:
                st.warning(f"⚠️ Only {analysis['coverage_pct']:.1f}% of the area is within the recommended "
                          f"service radius of {GOVERNMENT_STANDARDS[facility_type]['service_radius_km']} km. "
                          "Consider better spatial distribution of facilities.")
            
            if facility_type == "parks" and "area_gap" in analysis:
                st.info(f"🌳 Total park area: {analysis['total_area']:,.0f} sqm | "
                      f"Required area: {analysis['required_area']:,.0f} sqm | "
                      f"Area gap: {analysis['area_gap']:,.0f} sqm")
        
        except Exception as e:
            st.error(f"Error processing data: {str(e)}")

if __name__ == "__main__":
    main()