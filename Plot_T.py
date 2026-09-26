import logging
import sys
from pathlib import Path
import pandas as pd
import folium
from folium.plugins import MarkerCluster, MiniMap

CSV_FILES = ["404_part1.csv", "404_part2.csv", "405_part1.csv", "405_part2.csv"]
OUTPUT_HTML_MAP = "towers_filtered_map.html"

DARK_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
DARK_TILE_ATTR = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"

LAT_MIN, LAT_MAX = 6.0, 37.5
LON_MIN, LON_MAX = 68.0, 97.5

INDIA_CENTER = [20.5937, 78.9629]
INITIAL_ZOOM = 5
# you can increase the marks per layer but it will increase the size of the HTML file 
MAX_MARKERS_PER_LAYER = 10000

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


class TelecomDataPipeline:
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

            if "lon" in df.columns and "long" not in df.columns:
                df.rename(columns={"lon": "long"}, inplace=True)

            if "net" in df.columns and "mnc" not in df.columns:
                df.rename(columns={"net": "mnc"}, inplace=True)

            dataframes.append(df)

        if not dataframes:
            logging.error("No valid CSV files were loaded.")
            raise FileNotFoundError("None of the specified CSV files were found.")

        combined_df = pd.concat(dataframes, ignore_index=True)

        combined_df["lat"] = pd.to_numeric(combined_df["lat"], errors="coerce")
        combined_df["long"] = pd.to_numeric(combined_df["long"], errors="coerce")
        combined_df.dropna(subset=["lat", "long"], inplace=True)

        combined_df = combined_df[
            (combined_df["lat"].between(LAT_MIN, LAT_MAX)) & 
            (combined_df["long"].between(LON_MIN, LON_MAX))
        ]

        if "radio" in combined_df.columns:
            combined_df["radio"] = combined_df["radio"].astype(str).str.upper().str.strip()
        else:
            combined_df["radio"] = "GSM"

        if "range" in combined_df.columns:
            combined_df["range"] = pd.to_numeric(combined_df["range"], errors="coerce").fillna(1000).astype(int)
        else:
            combined_df["range"] = 1000

        if "mnc" in combined_df.columns:
            combined_df["mnc"] = pd.to_numeric(combined_df["mnc"], errors="coerce")
            combined_df["operator"] = combined_df["mnc"].map(OPERATOR_MNC_MAP).fillna("Other / Regional")
        else:
            combined_df["operator"] = "Unknown Operator"

        logging.info("Successfully processed %d cell towers within India boundaries.", len(combined_df))
        return combined_df


class IndiaTowerMapBuilder:
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

        operators = self.df["operator"].unique() if not self.df.empty else []

        for operator in operators:
            op_df = self.df[self.df["operator"] == operator]
            if len(op_df) > MAX_MARKERS_PER_LAYER:
                op_df = op_df.sample(MAX_MARKERS_PER_LAYER, random_state=42)

            op_group = folium.FeatureGroup(name=f"🏢 Operator: {operator} ({len(op_df):,})")
            cluster = MarkerCluster(disableClusteringAtZoom=14).add_to(op_group)

            for row in op_df.itertuples(index=False):
                popup_html = f"""
                <div style="font-family: Arial, sans-serif; width: 190px;">
                    <h4 style="margin: 0 0 5px 0; color: #0078A8;"><b>{row.operator}</b></h4>
                    <hr style="margin: 5px 0;">
                    <b>Radio:</b> {getattr(row, 'radio', 'N/A')}<br>
                    <b>Latitude:</b> {row.lat:.5f}<br>
                    <b>Longitude:</b> {row.long:.5f}<br>
                    <b>Range:</b> {getattr(row, 'range', 1000):,} meters
                </div>
                """
                folium.Marker(
                    location=[row.lat, row.long],
                    popup=folium.Popup(popup_html, max_width=220),
                    tooltip=f"{row.operator} ({getattr(row, 'radio', 'Cell Tower')})"
                ).add_to(cluster)

            op_group.add_to(map_canvas)

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