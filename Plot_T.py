import folium
from folium.plugins import FastMarkerCluster
import pandas as pd
from pathlib import Path

# 1. Read CSV
data_path = Path(__file__).with_name(
    "guj_network_tower_with_Network_provider_and_lat_long.csv"
)
data = pd.read_csv(data_path)

# Clean column strings
data['radio'] = data['radio'].astype(str).str.strip()

# 2. Filter for GSM and LTE only
data = data[data['radio'].isin(['GSM', 'LTE'])]

# 3. Filter for UGVCL region (North Gujarat)
ugvcl_bounds = (
    (data['lat'] >= 22.8) & (data['lat'] <= 24.7) &
    (data['long'] >= 71.1) & (data['long'] <= 74.0)
)
data = data[ugvcl_bounds].copy()

# Clean & sanitize 'range' column (in meters)
data['range'] = pd.to_numeric(data['range'], errors='coerce').fillna(1000)
data['range'] = data['range'].clip(lower=100, upper=5000)

# 4. Create base map with Canvas rendering enabled
center_lat = data["lat"].mean()
center_lon = data["long"].mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=9, prefer_canvas=True)

# 5. Fast JS Callback function for instant rendering on click
callback = """
function (row) {
    var lat = row[0];
    var lng = row[1];
    var range = row[2];
    var company = row[3];
    var radio = row[4];
    var color = (radio === 'LTE') ? '#007bff' : '#28a745';

    var marker = L.circleMarker([lat, lng], {
        radius: 5,
        fillColor: color,
        color: '#ffffff',
        weight: 1,
        fillOpacity: 0.9
    });

    var popupContent = `
        <div style="font-family: Arial, sans-serif; font-size: 13px; width: 190px; line-height: 1.4;">
            <h4 style="margin: 0 0 6px 0; color: #333; border-bottom: 1px solid #ccc; padding-bottom: 4px;">📡 Tower Info</h4>
            <b>TSP / Company:</b> ${company}<br>
            <b>Type:</b> <span style="color: ${color}; font-weight: bold;">${radio}</span><br>
            <b>Coverage Range:</b> ${range} m (${(range/1000).toFixed(2)} km)<br>
            <b>Coordinates:</b> ${lat.toFixed(4)}, ${lng.toFixed(4)}
        </div>
    `;

    marker.bindPopup(popupContent);
    marker.bindTooltip(`${company} (${radio}) | Range: ${range}m`);
    return marker;
}
"""

# 6. Group data into GSM and LTE arrays
gsm_data = data[data['radio'] == 'GSM'][['lat', 'long', 'range', 'Company', 'radio']].values.tolist()
lte_data = data[data['radio'] == 'LTE'][['lat', 'long', 'range', 'Company', 'radio']].values.tolist()

# 7. Add lightweight cluster layers
gsm_layer = folium.FeatureGroup(name="GSM Towers")
gsm_layer.add_child(FastMarkerCluster(gsm_data, callback=callback))

lte_layer = folium.FeatureGroup(name="LTE Towers")
lte_layer.add_child(FastMarkerCluster(lte_data, callback=callback))

m.add_child(gsm_layer)
m.add_child(lte_layer)

# 8. Add Layer Controls
folium.LayerControl(collapsed=False).add_to(m)

# 9. Save output
m.save("ugvcl_towers_filtered_map.html")
print("Ultra-lightweight map generated! Map runs completely smooth and loads instantly.")