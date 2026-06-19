from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

PROJECT_DIR = Path(__file__).resolve().parent
DATA_PATH = PROJECT_DIR / "data" / "entsoe_crossborder_flows.csv"
OUTPUT_HTML = PROJECT_DIR / "cross_border_flows.html"
OUTPUT_PNG = PROJECT_DIR / "cross_border_flows.png"

COUNTRY_COORDS = {
    'Germany': (51.1657, 10.4515),
    'France': (46.2276, 2.2137),
    'Netherlands': (52.1326, 5.2913),
    'Austria': (47.5162, 14.5501),
    'Poland': (51.9194, 19.1451),
    'Denmark': (56.2639, 9.5018),
    'Switzerland': (46.8182, 8.2275),
}

ISO_TO_COUNTRY = {
    'FR': 'France',
    'NL': 'Netherlands',
    'AT': 'Austria',
    'PL': 'Poland',
    'DK': 'Denmark',
    'CH': 'Switzerland',
}


def load_entsoe_flows(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing ENTSO-E flow CSV: {path}")

    df = pd.read_csv(path, parse_dates=['hour_utc'])
    df['net_flow_mwh'] = df['total_exports_mwh'] - df['total_imports_mwh']
    return df


def compute_average_neighbor_flows(df: pd.DataFrame) -> dict[str, float]:
    grouped = df.groupby('neighbor')['net_flow_mwh'].mean()
    return {
        ISO_TO_COUNTRY[neighbor]: float(flow)
        for neighbor, flow in grouped.items()
        if neighbor in ISO_TO_COUNTRY
    }


def build_figure(flows: dict[str, float]) -> go.Figure:
    fig = go.Figure()
    germany_lat, germany_lon = COUNTRY_COORDS['Germany']

    max_flow = max(abs(v) for v in flows.values()) if flows else 1
    width_scale = 10 / max_flow

    for country, flow in flows.items():
        if country not in COUNTRY_COORDS:
            continue

        color = '#74C476' if flow > 0 else '#EF6548'
        width = max(1, abs(flow) * width_scale)

        target_lat, target_lon = COUNTRY_COORDS[country]
        fig.add_trace(
            go.Scattergeo(
                lon=[germany_lon, target_lon],
                lat=[germany_lat, target_lat],
                mode='lines',
                line=dict(width=width, color=color),
                hovertemplate=f"{country}: {flow:.0f} MWh<br>Average net flow (DE perspective)<extra></extra>",
                name=country,
                showlegend=False,
            )
        )

    for country, (lat, lon) in COUNTRY_COORDS.items():
        marker_size = 14 if country == 'Germany' else 8
        text = 'DE' if country == 'Germany' else country

        fig.add_trace(
            go.Scattergeo(
                lon=[lon],
                lat=[lat],
                mode='markers+text',
                marker=dict(size=marker_size, color='white', line=dict(width=1, color='#444')),
                text=[text],
                textposition='top center',
                textfont=dict(color='white', size=11),
                showlegend=False,
            )
        )

    fig.update_layout(
        title_text='Average Germany Net Cross-Border Flow by Neighbor',
        title_x=0.02,
        title_font=dict(size=20, color='white'),
        paper_bgcolor='#1A1A2E',
        plot_bgcolor='#1A1A2E',
        geo=dict(
            bgcolor='#1A1A2E',
            showland=True,
            landcolor='#16213E',
            showocean=True,
            oceancolor='#0F3460',
            showcoastlines=True,
            coastlinecolor='#444466',
            projection_type='natural earth',
            center=dict(lat=51, lon=10),
            projection_scale=4,
        ),
        font=dict(color='white'),
        width=1000,
        height=600,
    )

    return fig


def main() -> None:
    flows_df = load_entsoe_flows(DATA_PATH)
    neighbor_flows = compute_average_neighbor_flows(flows_df)

    if not neighbor_flows:
        raise ValueError('No neighbor flows found in ENTSO-E CSV')

    fig = build_figure(neighbor_flows)
    fig.write_html(OUTPUT_HTML)
    fig.write_image(OUTPUT_PNG)
    fig.show()


if __name__ == '__main__':
    main()
