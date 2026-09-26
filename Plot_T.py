"""
===============================================================================
All-India Cellular Network Tower Visualizer
===============================================================================
File        : Plot_T.py
Datasets    : 404.csv, 405.csv
Description : Processes nationwide OpenCellID data from MCC 404 and 405 CSV files,
              maps India telecom operators (Airtel, Jio, Vi, BSNL) and radio 
              technologies (GSM, LTE, 5G NR), rendering an interactive Folium map.
===============================================================================
"""

import logging
import sys
from pathlib import Path
import pandas as pd
import folium
from folium.plugins import FastMarkerCluster, MiniMap

# -----------------------------------------------------------------------------
# CONFIGURATION CONSTANTS
# -----------------------------------------------------------------------------
CSV_FILES = ["404_part1.csv", "404_part2.csv", "405_part1.csv", "405_part2.csv"]
OUTPUT_HTML_MAP = "towers_filtered_map.html"

# Keyless Dark Map Tile URL (Esri Dark Gray Canvas)
DARK_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
DARK_TILE_ATTR = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"

# All-India Geographic Bounding Box
LAT_MIN, LAT_MAX = 6.0, 37.5
LON_MIN, LON_MAX = 68.0, 97.5


INDIA_CENTER = [20.5937, 78.9629]
INITIAL_ZOOM = 5
MAX_MARKERS_PER_LAYER = 30_000  # Cap per layer for fast browser rendering

# Mobile Network Code (MNC / 'mnc' / 'net') mapping for Indian Operators
OPERATOR_MNC_MAP = {
    10: "Airtel", 45: "Airtel", 90: "Airtel", 98: "Airtel",
    5: "Vodafone Idea", 20: "Vodafone Idea", 22: "Vodafone Idea",
    861: "Jio", 872: "Jio", 854: "Jio",
    51: "BSNL", 57: "BSNL", 66: "BSNL"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


# -----------------------------------------------------------------------------
# DATA PIPELINE
# -----------------------------------------------------------------------------
class TelecomDataPipeline:
    """Loads, combines, cleans, and filters MCC datasets (404.csv, 405.csv)."""

    def __init__(self, filepaths: list[str]):
        self.filepaths = [Path(f) for f in filepaths]

    def process(self) -> pd.DataFrame:
        dataframes = []

        for path in self.filepaths:
            if not path.exists():
                logging.warning("File '%s' not found. Skipping...", path)
                continue

            logging.info("Reading dataset: %s", path)
            df = pd.read_csv(path)
            df.columns = [col.lower().strip() for col in df.columns]

            # Standardize longitude column name ('lon' vs 'long')
            if "lon" in df.columns and "long" not in df.columns:
                df.rename(columns={"lon": "long"}, inplace=True)

            # Standardize MNC column name ('net' vs 'mnc')
            if "net" in df.columns and "mnc" not in df.columns:
                df.rename(columns={"net": "mnc"}, inplace=True)

            dataframes.append(df)

        if not dataframes:
            logging.error("No valid CSV files were loaded.")
            raise FileNotFoundError("None of the specified CSV files were found.")

        # Combine all loaded CSVs
        combined_df = pd.concat(dataframes, ignore_index=True)

        # Cast coordinates and drop missing rows
        combined_df["lat"] = pd.to_numeric(combined_df["lat"], errors="coerce")
        combined_df["long"] = pd.to_numeric(combined_df["long"], errors="coerce")
        combined_df.dropna(subset=["lat", "long"], inplace=True)

        # Bounding Box Filter for India Geographic Boundaries
        combined_df = combined_df[
            (combined_df["lat"].between(LAT_MIN, LAT_MAX)) & 
            (combined_df["long"].between(LON_MIN, LON_MAX))
        ]

        # Radio Technology Cleaning
        if "radio" in combined_df.columns:
            combined_df["radio"] = combined_df["radio"].astype(str).str.upper().str.strip()
        else:
            combined_df["radio"] = "GSM"

        # Map MNC ('net' / 'mnc') to Operator Name
        if "mnc" in combined_df.columns:
            combined_df["mnc"] = pd.to_numeric(combined_df["mnc"], errors="coerce")
            combined_df["operator"] = combined_df["mnc"].map(OPERATOR_MNC_MAP).fillna("Other / Regional")
        else:
            combined_df["operator"] = "Unknown Operator"

        logging.info("Successfully processed %d cell towers within India boundaries.", len(combined_df))
        return combined_df


# -----------------------------------------------------------------------------
# GEOSPATIAL MAP RENDERER
# -----------------------------------------------------------------------------
class IndiaTowerMapBuilder:
    """Renders interactive Folium map with independent Operator and Technology layer controls."""

    def __init__(self, data: pd.DataFrame):
        self.df = data

    def build_map(self, output_path: str):
        logging.info("Initializing Map Canvas centered on India...")

        map_canvas = folium.Map(
            location=INDIA_CENTER,
            zoom_start=INITIAL_ZOOM,
            tiles=DARK_TILE_URL,
            attr=DARK_TILE_ATTR,
            prefer_canvas=True
        )

        # ---------------------------------------------------------------------
        # 1. OPERATOR FEATURE GROUPS
        # ---------------------------------------------------------------------
        operators = self.df["operator"].unique() if not self.df.empty else []
        
        for operator in operators:
            op_df = self.df[self.df["operator"] == operator]
            if len(op_df) > MAX_MARKERS_PER_LAYER:
                op_df = op_df.sample(MAX_MARKERS_PER_LAYER, random_state=42)

            op_group = folium.FeatureGroup(name=f"🏢 Operator: {operator} ({len(op_df):,})")
            coords = op_df[["lat", "long"]].values.tolist()

            FastMarkerCluster(
                data=coords,
                disableClusteringAtZoom=14
            ).add_to(op_group)

            op_group.add_to(map_canvas)

        # ---------------------------------------------------------------------
        # 2. TECHNOLOGY FEATURE GROUPS
        # ---------------------------------------------------------------------
        technologies = self.df["radio"].unique() if not self.df.empty else []

        for tech in technologies:
            tech_df = self.df[self.df["radio"] == tech]
            if len(tech_df) > MAX_MARKERS_PER_LAYER:
                tech_df = tech_df.sample(MAX_MARKERS_PER_LAYER, random_state=42)

            tech_group = folium.FeatureGroup(
                name=f"📡 Tech: {tech} ({len(tech_df):,})", 
                show=False
            )
            coords = tech_df[["lat", "long"]].values.tolist()

            FastMarkerCluster(
                data=coords,
                disableClusteringAtZoom=14
            ).add_to(tech_group)

            tech_group.add_to(map_canvas)

        # UI Additions
        folium.LayerControl(collapsed=False).add_to(map_canvas)
        
        minimap_layer = folium.TileLayer(
            tiles=DARK_TILE_URL,
            attr=DARK_TILE_ATTR,
            name="MiniMap Base"
        )
        MiniMap(
            tile_layer=minimap_layer,
            toggle_display=True
        ).add_to(map_canvas)

        map_canvas.save(output_path)
        logging.info("Interactive map saved to: %s", output_path)


# -----------------------------------------------------------------------------
# MAIN EXECUTION ENTRYPOINT
# -----------------------------------------------------------------------------
def main():
    try:
        pipeline = TelecomDataPipeline(CSV_FILES)
        df_cleaned = pipeline.process()

        builder = IndiaTowerMapBuilder(df_cleaned)
        builder.build_map(OUTPUT_HTML_MAP)

        logging.info("All-India map generated successfully!")

    except Exception as err:
        logging.error("Execution failed: %s", str(err))


if __name__ == "__main__":
    main()