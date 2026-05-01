import pandas as pd
from dash import Dash, html, dcc, dash_table, Input, Output, State, callback, callback_context
import plotly.express as px
import unicodedata
import re
import ast

# ---------------------------------------------------------
# READ FILES
# ---------------------------------------------------------

PaperCounts = pd.read_csv("tiered_openalex_counts_by_university_category_seed.csv")
Top5Papers = pd.read_csv("tiered_openalex_top5_titles.csv")

# NEW — includes Category + Seed + year + patent_count
PatentYears = pd.read_csv("patent_counts_by_year_category_seed_institution.csv")

# NEW — includes top_patents list
Top5Patents = pd.read_csv("tiered_patent_top5_full.csv")

locations = pd.read_csv("r1_r2_coordinates.csv", encoding="latin1")

# ---------------------------------------------------------
# PARSE STRINGIFIED LISTS IN TOP‑5 FILES
# ---------------------------------------------------------

def parse_list_column(df, colname):
    df[colname] = df[colname].apply(
        lambda x: ast.literal_eval(x) if isinstance(x, str) else (x if isinstance(x, list) else [])
    )
    return df

Top5Papers = parse_list_column(Top5Papers, "top_works")
Top5Patents = parse_list_column(Top5Patents, "top_patents")

# ---------------------------------------------------------
# STRONG UNIVERSITY NAME NORMALIZATION
# ---------------------------------------------------------

def normalize_univ(x):
    if pd.isna(x):
        return ""
    x = str(x)

    x = x.lower()
    x = unicodedata.normalize("NFKC", x)
    x = x.replace("\u200b", "").replace("\xa0", " ")
    x = x.replace("–", "-").replace("—", "-")
    x = x.replace("`", "'").replace("’", "'").replace("‘", "'")
    x = x.replace("“", '"').replace("”", '"')
    x = re.sub(r"\s+", " ", x)

    return x.strip()

for df in [PaperCounts, PatentYears, Top5Papers, Top5Patents, locations]:
    df["University"] = df["University"].apply(normalize_univ)

# ---------------------------------------------------------
# FIX COORDINATE COLUMN NAMES
# ---------------------------------------------------------

locations = locations.rename(columns={
    "LATITUDE": "Latitude",
    "LONGITUDE": "Longitude",
    "latitude": "Latitude",
    "longitude": "Longitude"
})

# ---------------------------------------------------------
# MERGE COORDINATES INTO PaperCounts + PatentYears
# ---------------------------------------------------------

PaperCounts = PaperCounts.merge(
    locations[["University", "Carnegie", "Latitude", "Longitude", "State"]],
    on="University",
    how="left",
    validate="many_to_one"
)

PatentYears = PatentYears.merge(
    locations[["University", "Carnegie", "Latitude", "Longitude", "State"]],
    on="University",
    how="left",
    validate="many_to_one"
)

# ---------------------------------------------------------
# FIX DUPLICATE MERGE COLUMNS
# ---------------------------------------------------------

def fix_merge_columns(df):
    if "Carnegie_y" in df.columns:
        df = df.drop(columns=["Carnegie_x"], errors="ignore")
        df = df.rename(columns={"Carnegie_y": "Carnegie"})
    if "State_y" in df.columns:
        df = df.drop(columns=["State_x"], errors="ignore")
        df = df.rename(columns={"State_y": "State"})
    return df

PaperCounts = fix_merge_columns(PaperCounts)
PatentYears = fix_merge_columns(PatentYears)

# ---------------------------------------------------------
# DROP ROWS MISSING COORDINATES
# ---------------------------------------------------------

PaperCounts = PaperCounts.dropna(subset=["Latitude", "Longitude"])
PatentYears = PatentYears.dropna(subset=["Latitude", "Longitude"])

# ---------------------------------------------------------
# BUILD TOP‑5 LOOKUP DICTIONARIES (WITH SEED)
# ---------------------------------------------------------

Top5PapersDict = {}
for _, entry in Top5Papers.iterrows():
    key = (entry["University"], entry["Category"])
    Top5PapersDict.setdefault(key, [])
    for w in entry["top_works"]:
        Top5PapersDict[key].append({
            "title": w.get("title", ""),
            "year": w.get("year", ""),
            "openalex_url": w.get("openalex_url", ""),
            "cited_by_count": w.get("cited_by_count", ""),
            "seed": entry.get("Seed", "")
        })

Top5PatentsDict = {}
for _, entry in Top5Patents.iterrows():
    key = (entry["University"], entry["Category"])
    Top5PatentsDict.setdefault(key, [])
    for p in entry["top_patents"]:
        Top5PatentsDict[key].append({
            "patent_id": p.get("patent_id", ""),
            "patent_title": p.get("patent_title", ""),
            "patent_date": p.get("patent_date", ""),
            "organization": p.get("organization", ""),
            "seed": entry.get("Seed", "")
        })

# ---------------------------------------------------------
# BUILD PAPER YEAR LIST (FROM TOP‑5 PAPERS)
# ---------------------------------------------------------

paper_years = sorted({
    int(w.get("year"))
    for _, entry in Top5Papers.iterrows()
    for w in entry["top_works"]
    if str(w.get("year", "")).isdigit()
})

# ---------------------------------------------------------
# BUILD PATENT YEAR LIST (FROM PatentYears)
# ---------------------------------------------------------

patent_years = sorted(PatentYears["year"].dropna().unique())

# ---------------------------------------------------------
# CATEGORY LISTS
# ---------------------------------------------------------

paper_categories = sorted(PaperCounts["Category"].dropna().unique())
patent_categories = sorted(PatentYears["Category"].dropna().unique())

# ---------------------------------------------------------
# CARNEGIE LIST
# ---------------------------------------------------------

all_carnegie = sorted(locations["Carnegie"].dropna().unique())

# ---------------------------------------------------------
# HELPER FUNCTION
# ---------------------------------------------------------

def strip_html(text):
    return re.sub(r"<.*?>", "", text)

# ---------------------------------------------------------
# Helper: Extract patent_id from top_patents list
# ---------------------------------------------------------

def extract_patent_id(top_patents):
    if isinstance(top_patents, list) and len(top_patents) > 0:
        first = top_patents[0]
        if isinstance(first, dict):
            return first.get("patent_id", "")
    return ""

# ---------------------------------------------------------
# REGIONS
# ---------------------------------------------------------

regions = {
    "All Regions": locations["State"].dropna().unique().tolist(),
    "Northeast": ["Maine","New Hampshire","Vermont","Massachusetts","Rhode Island","Connecticut","New York","New Jersey","Pennsylvania"],
    "Midwest": ["Ohio","Michigan","Indiana","Illinois","Wisconsin","Minnesota","Iowa","Missouri","North Dakota","South Dakota","Nebraska","Kansas"],
    "South": ["Delaware","Maryland","Virginia","West Virginia","Kentucky","North Carolina","South Carolina","Tennessee","Georgia","Florida","Alabama","Mississippi","Arkansas","Louisiana","Texas","Oklahoma"],
    "West": ["Washington","Oregon","California","Nevada","Idaho","Montana","Wyoming","Utah","Colorado","Arizona","New Mexico","Alaska","Hawaii"]
}



# ---------------------------------------------------------
# MAP GENERATORS — FINAL VERSION (RAINBOW HEATMAPS + BLACK DOTS)
# ---------------------------------------------------------

# ---------------------------------------------------------
# BUILD HOVER TEXT FOR PAPERS
# ---------------------------------------------------------
def build_paper_hover(univ, df):
    lines = []

    carnegie = df["Carnegie"].iloc[0]
    display_univ = univ.title()

    lines.append(f"<b>{display_univ}</b>")
    lines.append(f"Carnegie: {carnegie}")
    lines.append("")

    cat_totals = (
        df.groupby("Category")["works_count"]
          .sum()
          .reset_index()
    )

    for _, row in cat_totals.iterrows():
        lines.append(f"{row['Category']}: {int(row['works_count'])} papers")

    return "<br>".join(lines)


# ---------------------------------------------------------
# BUILD HOVER TEXT FOR PATENTS
# ---------------------------------------------------------
def build_patent_hover(univ, df):
    lines = []

    carnegie = df["Carnegie"].iloc[0]
    display_univ = univ.title()

    lines.append(f"<b>{display_univ}</b>")
    lines.append(f"Carnegie: {carnegie}")
    lines.append("")

    cat_totals = (
        df.groupby("Category")["patent_count"]
          .sum()
          .reset_index()
    )

    for _, row in cat_totals.iterrows():
        lines.append(f"{row['Category']}: {int(row['patent_count'])} patents")

    return "<br>".join(lines)


# ---------------------------------------------------------
# PAPERS MAP (RAINBOW HEATMAP + BLACK DOTS)
# ---------------------------------------------------------
def generate_papers_map(df):
    if df.empty:
        return px.scatter_map(pd.DataFrame({"lat": [], "lon": []}), lat="lat", lon="lon")

    agg = (
        df.groupby(["University", "Latitude", "Longitude"])
          ["works_count"]
          .sum()
          .reset_index()
    )

    hover_dict = {
        univ: build_paper_hover(univ, df[df["University"] == univ])
        for univ in agg["University"].unique()
    }

    agg["hover"] = agg["University"].map(hover_dict)

    # Rainbow heatmap
    fig = px.density_map(
        agg,
        lat="Latitude",
        lon="Longitude",
        z="works_count",
        zoom=3,
        color_continuous_scale="Rainbow"
    )

    # Black dots
    fig.add_scattermap(
        lat=agg["Latitude"],
        lon=agg["Longitude"],
        mode="markers",
        marker=dict(size=8, color="black"),
        text=agg["hover"]
    )

    fig.update_layout(map_style="carto-positron")
    return fig


# ---------------------------------------------------------
# PATENTS MAP (RAINBOW HEATMAP + BLACK DOTS)
# ---------------------------------------------------------
def generate_patents_map(df):
    if df.empty:
        return px.scatter_map(pd.DataFrame({"lat": [], "lon": []}), lat="lat", lon="lon")

    agg = (
        df.groupby(["University", "Latitude", "Longitude"])
          ["patent_count"]
          .sum()
          .reset_index()
    )

    hover_dict = {
        univ: build_patent_hover(univ, df[df["University"] == univ])
        for univ in agg["University"].unique()
    }

    agg["hover"] = agg["University"].map(hover_dict)

    # Rainbow heatmap
    fig = px.density_map(
        agg,
        lat="Latitude",
        lon="Longitude",
        z="patent_count",
        zoom=3,
        color_continuous_scale="Rainbow"
    )

    # Black dots
    fig.add_scattermap(
        lat=agg["Latitude"],
        lon=agg["Longitude"],
        mode="markers",
        marker=dict(size=8, color="black"),
        text=agg["hover"]
    )

    fig.update_layout(map_style="carto-positron")
    return fig


# ---------------------------------------------------------
# COMBINED MAP (RAINBOW HEATMAP + BLACK DOTS)
# ---------------------------------------------------------
def generate_combined_map(df_papers, df_patents):

    # Aggregate papers
    agg_p = (
        df_papers.groupby(["University", "Latitude", "Longitude"])
                 ["works_count"]
                 .sum()
                 .reset_index()
    )

    # Aggregate patents
    agg_t = (
        df_patents.groupby(["University", "Latitude", "Longitude"])
                  ["patent_count"]
                  .sum()
                  .reset_index()
    )

    # Merge totals
    merged = pd.merge(
        agg_p,
        agg_t,
        on=["University", "Latitude", "Longitude"],
        how="outer"
    ).fillna(0)

    merged["total"] = merged["works_count"] + merged["patent_count"]

    # Hover text
    hover_dict = {}
    for univ in merged["University"].unique():
        p = int(merged.loc[merged["University"] == univ, "works_count"].iloc[0])
        t = int(merged.loc[merged["University"] == univ, "patent_count"].iloc[0])
        hover_dict[univ] = (
            f"<b>{univ.title()}</b><br>"
            f"Papers: {p}<br>"
            f"Patents: {t}<br>"
            f"Total: {p+t}"
        )

    merged["hover"] = merged["University"].map(hover_dict)

    # Rainbow heatmap (total output)
    fig = px.density_map(
        merged,
        lat="Latitude",
        lon="Longitude",
        z="total",
        zoom=3,
        color_continuous_scale="Rainbow"
    )

    # Black dots
    fig.add_scattermap(
        lat=merged["Latitude"],
        lon=merged["Longitude"],
        mode="markers",
        marker=dict(
            size=8,
            color="black",
            opacity=0.85
        ),
        text=merged["hover"]
    )

    fig.update_layout(map_style="carto-positron")
    return fig


# ---------------------------------------------------------
# LAYOUT (MAPS + TABLES + SEARCH + PATENT OUTPUT OVER TIME)
# ---------------------------------------------------------

map = Dash(__name__)

map.layout = html.Div([

    html.H1("University Research & Innovation Dashboard"),

    # -----------------------------------------------------
    # TABS
    # -----------------------------------------------------
    dcc.Tabs(
        id="map-tabs",
        value="papers-tab",
        children=[
            dcc.Tab(label="Papers Map", value="papers-tab"),
            dcc.Tab(label="Patents Map", value="patents-tab"),
            dcc.Tab(label="Combined Map", value="combined-tab"),
        ]
    ),

    # -----------------------------------------------------
    # PAPERS TAB CONTENT
    # -----------------------------------------------------
    html.Div(id="papers-tab-content", children=[

        html.H3("Papers Map Filters"),

        dcc.Dropdown(
            id="papers-category-filter",
            options=[{"label": c, "value": c} for c in paper_categories],
            multi=True,
            placeholder="Select categories...",
            style={"marginTop": "10px", "width": "400px"},
        ),

        html.Div(
            "Papers from 2019 to 2024",
            style={"fontWeight": "bold", "marginTop": "15px", "marginBottom": "20px"}
        ),

        dcc.Graph(id="papers-map"),

        html.Hr(),

        html.H2(
            id="selected-university-title-papers",
            children="Select a university on the papers map"
        ),

        dash_table.DataTable(
            id="university-table-papers",
            columns=[
                {"name": "Title", "id": "title"},
                {"name": "Type", "id": "type"},
                {"name": "Category", "id": "category"},
                {"name": "Subcategory", "id": "Seed"},
                {"name": "Year", "id": "year"},
                {"name": "ID", "id": "work_id"},
            ],
            data=[],
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "whiteSpace": "normal", "height": "auto"},
        ),
    ]),

    # -----------------------------------------------------
    # PATENTS TAB CONTENT
    # -----------------------------------------------------
    html.Div(id="patents-tab-content", style={"display": "none"}, children=[

        html.H3("Patents Map Filters"),

        dcc.Dropdown(
            id="patents-category-filter",
            options=[{"label": c, "value": c} for c in patent_categories],
            multi=True,
            placeholder="Select categories...",
            style={"marginTop": "10px", "width": "400px"},
        ),

        html.Div([
            html.Label("Filter Patents by Year:", style={"fontWeight": "bold"}),
            dcc.RangeSlider(
                id="patent-year-slider",
                min=min(patent_years),
                max=max(patent_years),
                value=[min(patent_years), max(patent_years)],
                marks={int(y): str(int(y)) for y in patent_years},
                step=1,
                allowCross=False,
                pushable=1,
            )
        ], style={"width": "600px", "marginTop": "20px", "marginBottom": "20px"}),

        dcc.Graph(id="patents-map"),

        html.Hr(),

        html.H2(
            id="selected-university-title-patents",
            children="Select a university on the patents map"
        ),

        dash_table.DataTable(
            id="university-table-patents",
            columns=[
                {"name": "Title", "id": "title"},
                {"name": "Type", "id": "type"},
                {"name": "Category", "id": "category"},
                {"name": "Subcategory", "id": "Seed"},
                {"name": "Year", "id": "year"},
                {"name": "ID", "id": "work_id"},
            ],
            data=[],
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "whiteSpace": "normal", "height": "auto"},
        ),
    ]),

    # -----------------------------------------------------
    # COMBINED TAB CONTENT
    # -----------------------------------------------------
    html.Div(id="combined-tab-content", style={"display": "none"}, children=[

        html.H3("Combined Papers + Patents Map Filters"),

        dcc.Dropdown(
            id="combined-category-filter",
            options=[{"label": c, "value": c}
                     for c in sorted(set(paper_categories + patent_categories))],
            multi=True,
            placeholder="Select categories...",
            style={"marginTop": "10px", "width": "400px"},
        ),

        html.Div(
            "Papers from 2019 to 2024",
            style={"fontWeight": "bold", "marginTop": "20px"}
        ),

        html.Div([
            html.Label("Filter Patents by Year:", style={"fontWeight": "bold"}),
            dcc.RangeSlider(
                id="combined-patent-year-slider",
                min=min(patent_years),
                max=max(patent_years),
                value=[min(patent_years), max(patent_years)],
                marks={int(y): str(int(y)) for y in patent_years},
                step=1,
                allowCross=False,
                pushable=1,
            )
        ], style={"width": "600px", "marginTop": "20px", "marginBottom": "20px"}),

        dcc.Graph(id="combined-map"),

        html.Hr(),

        html.H2(
            id="selected-university-title-combined",
            children="Select a university on the combined map"
        ),

        dash_table.DataTable(
            id="university-table-combined",
            columns=[
                {"name": "Title", "id": "title"},
                {"name": "Type", "id": "type"},
                {"name": "Category", "id": "category"},
                {"name": "Subcategory", "id": "Seed"},
                {"name": "Year", "id": "year"},
                {"name": "ID", "id": "work_id"},
            ],
            data=[],
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "whiteSpace": "normal", "height": "auto"},
        ),
    ]),

    html.Hr(),

    # -----------------------------------------------------
    # SEARCH SECTION
    # -----------------------------------------------------
    html.H2("Search Papers and Patents"),

    dcc.Dropdown(
        id="search-category",
        options=[{"label": c, "value": c}
                 for c in sorted(set(paper_categories + patent_categories))],
        multi=True,
        placeholder="Filter by category...",
        style={"width": "600px", "marginBottom": "20px"}
    ),

    html.Div(
        "Papers from 2019 to 2024",
        style={"fontWeight": "bold", "marginBottom": "30px"}
    ),

    html.Div([
        html.Div([
            html.Label("Content Type", style={"fontWeight": "bold"}),
            dcc.Dropdown(
                id="content",
                options=[
                    {"label": "Papers Only", "value": "papers"},
                    {"label": "Patents Only", "value": "patents"},
                    {"label": "Both", "value": "both"},
                ],
                value="both",
                clearable=False,
                style={"width": "180px"}
            ),
        ], style={"marginRight": "30px"}),

        html.Div([
            html.Label("Carnegie", style={"fontWeight": "bold"}),
            dcc.Dropdown(
                id="carnegie-filter",
                options=[{"label": "R1 and R2", "value": "All"}] +
                        [{"label": c, "value": c} for c in all_carnegie],
                value="All",
                clearable=False,
                style={"width": "180px"}
            ),
        ], style={"marginRight": "30px"}),

        html.Div([
            html.Label("Number of Rows", style={"fontWeight": "bold"}),
            dcc.Input(
                id="NUniversities",
                type="number",
                value=10,
                min=1,
                max=500,
                style={"width": "120px"}
            ),
        ]),
    ], style={"display": "flex", "flexWrap": "wrap", "marginBottom": "20px"}),

    html.Div([
        html.Label("Keyword Search", style={"fontWeight": "bold"}),
        dcc.Input(
            id="search-university",
            type="text",
            placeholder="Search title, university, category, ID, state...",
            style={"width": "500px", "marginTop": "5px"}
        ),
    ], style={"marginBottom": "25px"}),

    dash_table.DataTable(
        id="search-results-table",
        columns=[
            {"name": "University", "id": "University"},
            {"name": "State", "id": "State"},
            {"name": "Carnegie", "id": "Carnegie"},
            {"name": "Category", "id": "Category"},
            {"name": "Subcategory", "id": "Seed"},
            {"name": "Papers", "id": "works_count"},
            {"name": "Patents", "id": "us_patents_count"},
            {"name": "Type", "id": "type"},
            {"name": "Title", "id": "title"},
            {"name": "Year", "id": "year"},
            {"name": "Citations", "id": "cited_by_count"},
            {"name": "ID", "id": "ID"},
        ],
        data=[],
        page_size=20,
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "whiteSpace": "normal", "height": "auto"},
    ),

    html.Hr(),

    # -----------------------------------------------------
    # UNIVERSITY PATENT OUTPUT OVER TIME
    # -----------------------------------------------------
    html.H2("University Patent Output Over Time"),

    html.Div(
        style={
            "display": "flex",
            "gap": "20px",
            "alignItems": "center",
            "marginTop": "15px",
            "marginBottom": "15px"
        },
        children=[

            dcc.Dropdown(
                id="patent-regionselect",
                options=[{"label": r, "value": r} for r in regions.keys()],
                value="All Regions",
                style={"width": "300px"}
            ),

            dcc.Input(
                id="patent-NUniversities",
                type="number",
                value=5,
                min=1,
                max=50,
                style={"width": "120px"}
            ),
        ],
    ),

    dcc.Input(
        id="patent-USearch",
        type="text",
        placeholder="Search university or state..."
    ),

    html.Div(id="patent-university-graphs"),

    html.Hr(),
])



# ---------------------------------------------------------
# CALLBACKS — MAPS + SEARCH (FULLY CORRECTED)
# ---------------------------------------------------------

# ---------------------------------------------------------
# TAB SWITCHING
# ---------------------------------------------------------

@map.callback(
    Output("papers-tab-content", "style"),
    Output("patents-tab-content", "style"),
    Output("combined-tab-content", "style"),
    Input("map-tabs", "value")
)
def toggle_tabs(tab):
    if tab == "papers-tab":
        return {"display": "block"}, {"display": "none"}, {"display": "none"}
    if tab == "patents-tab":
        return {"display": "none"}, {"display": "block"}, {"display": "none"}
    if tab == "combined-tab":
        return {"display": "none"}, {"display": "none"}, {"display": "block"}
    return {"display": "block"}, {"display": "none"}, {"display": "none"}


# ---------------------------------------------------------
# PAPERS MAP CALLBACK (RAINBOW HEATMAP + BLACK DOTS)
# ---------------------------------------------------------

@map.callback(
    Output("papers-map", "figure"),
    Input("papers-category-filter", "value")
)
def update_papers_map(category_list):

    df = PaperCounts.copy()

    if category_list:
        df = df[df["Category"].isin(category_list)]

    if df.empty:
        fig = px.scatter_map(pd.DataFrame({"lat": [], "lon": []}), lat="lat", lon="lon")
        fig.update_layout(map_style="carto-positron", mapbox_zoom=3)
        return fig

    agg = (
        df.groupby(["University", "Latitude", "Longitude"])
          ["works_count"]
          .sum()
          .reset_index()
    )

    hover_dict = {
        univ: build_paper_hover(univ, df[df["University"] == univ])
        for univ in agg["University"].unique()
    }
    agg["hover"] = agg["University"].map(hover_dict)

    fig = px.density_map(
        agg,
        lat="Latitude",
        lon="Longitude",
        z="works_count",
        zoom=3,
        color_continuous_scale="Rainbow"
    )

    fig.add_scattermap(
        lat=agg["Latitude"],
        lon=agg["Longitude"],
        mode="markers",
        marker=dict(size=8, color="black"),
        text=agg["hover"]
    )

    fig.update_layout(map_style="carto-positron")
    return fig


# ---------------------------------------------------------
# PATENTS MAP CALLBACK (RAINBOW HEATMAP + BLACK DOTS)
# ---------------------------------------------------------

@map.callback(
    Output("patents-map", "figure"),
    Input("patents-category-filter", "value"),
    Input("patent-year-slider", "value")
)
def update_patents_map(category_list, year_range):

    y_min, y_max = year_range

    df = PatentYears.copy()
    df = df[(df["year"] >= y_min) & (df["year"] <= y_max)]

    if category_list:
        df = df[df["Category"].isin(category_list)]

    if df.empty:
        fig = px.scatter_map(pd.DataFrame({"lat": [], "lon": []}), lat="lat", lon="lon")
        fig.update_layout(map_style="carto-positron", mapbox_zoom=3)
        return fig

    agg = (
        df.groupby(["University", "Latitude", "Longitude"])
          ["patent_count"]
          .sum()
          .reset_index()
    )

    hover_dict = {
        univ: build_patent_hover(univ, df[df["University"] == univ])
        for univ in agg["University"].unique()
    }
    agg["hover"] = agg["University"].map(hover_dict)

    fig = px.density_map(
        agg,
        lat="Latitude",
        lon="Longitude",
        z="patent_count",
        zoom=3,
        color_continuous_scale="Rainbow"
    )

    fig.add_scattermap(
        lat=agg["Latitude"],
        lon=agg["Longitude"],
        mode="markers",
        marker=dict(size=8, color="black"),
        text=agg["hover"]
    )

    fig.update_layout(map_style="carto-positron")
    return fig


# ---------------------------------------------------------
# COMBINED MAP CALLBACK (RAINBOW HEATMAP + BLACK DOTS)
# ---------------------------------------------------------

@map.callback(
    Output("combined-map", "figure"),
    Input("combined-category-filter", "value"),
    Input("combined-patent-year-slider", "value"),
)
def update_combined_map(category_list, patent_year_range):

    t_min, t_max = patent_year_range

    df_p = PaperCounts.copy()
    df_t = PatentYears.copy()
    df_t = df_t[(df_t["year"] >= t_min) & (df_t["year"] <= t_max)]

    if category_list:
        df_p = df_p[df_p["Category"].isin(category_list)]
        df_t = df_t[df_t["Category"].isin(category_list)]

    if df_p.empty and df_t.empty:
        fig = px.scatter_map(pd.DataFrame({"lat": [], "lon": []}), lat="lat", lon="lon")
        fig.update_layout(map_style="carto-positron", mapbox_zoom=3)
        return fig

    agg_p = (
        df_p.groupby(["University", "Latitude", "Longitude"])
            ["works_count"]
            .sum()
            .reset_index()
    )

    agg_t = (
        df_t.groupby(["University", "Latitude", "Longitude"])
            ["patent_count"]
            .sum()
            .reset_index()
    )

    merged = pd.merge(
        agg_p,
        agg_t,
        on=["University", "Latitude", "Longitude"],
        how="outer"
    ).fillna(0)

    merged["total"] = merged["works_count"] + merged["patent_count"]

    hover_dict = {}
    for univ in merged["University"].unique():
        p = int(merged.loc[merged["University"] == univ, "works_count"].iloc[0])
        t = int(merged.loc[merged["University"] == univ, "patent_count"].iloc[0])
        hover_dict[univ] = (
            f"<b>{univ.title()}</b><br>"
            f"Papers: {p}<br>"
            f"Patents: {t}<br>"
            f"Total: {p+t}"
        )

    merged["hover"] = merged["University"].map(hover_dict)

    fig = px.density_map(
        merged,
        lat="Latitude",
        lon="Longitude",
        z="total",
        zoom=3,
        color_continuous_scale="Rainbow"
    )

    fig.add_scattermap(
        lat=merged["Latitude"],
        lon=merged["Longitude"],
        mode="markers",
        marker=dict(
            size=8,
            color="black",
            opacity=0.85
        ),
        text=merged["hover"]
    )

    fig.update_layout(map_style="carto-positron")
    return fig


# =====================================================================
# SELECTED UNIVERSITY TABLE — PAPERS MAP
# =====================================================================
@map.callback(
    Output("selected-university-title-papers", "children"),
    Output("university-table-papers", "data"),
    Input("papers-map", "clickData"),
    Input("papers-category-filter", "value"),
    Input("search-category", "value"),
    Input("carnegie-filter", "value"),
)
def update_papers_table(click, papers_map_filter, categories, carnegie):

    if not click or "points" not in click:
        return "Select a university on the papers map", []

    hover_html = click["points"][0]["text"]
    first_line = hover_html.split("<br>")[0]
    clean_univ = strip_html(first_line)
    univ_key = normalize_univ(clean_univ)

    rows = []

    # Carnegie filter
    if carnegie != "All":
        df_car = PaperCounts[PaperCounts["University"] == univ_key]
        if df_car.empty or df_car["Carnegie"].iloc[0] != carnegie:
            return f"Selected University: {clean_univ}", []

    # Build rows from Top5PapersDict
    for (u, category), works in Top5PapersDict.items():
        if u != univ_key:
            continue
        if papers_map_filter and category not in papers_map_filter:
            continue
        if categories and category not in categories:
            continue

        for w in works:
            rows.append({
                "title": w["title"],
                "type": "paper",
                "category": category,
                "Seed": w.get("seed", ""),
                "year": w.get("year", ""),
                "work_id": w.get("openalex_url", "")
            })

    if not rows:
        return f"Selected University: {clean_univ}", []

    df = pd.DataFrame(rows).sort_values("year", ascending=False)
    return f"Selected University: {clean_univ}", df.to_dict("records")


# =====================================================================
# SELECTED UNIVERSITY TABLE — PATENTS MAP (FIXED TITLES)
# =====================================================================
@map.callback(
    Output("selected-university-title-patents", "children"),
    Output("university-table-patents", "data"),
    Input("patents-map", "clickData"),
    Input("patents-category-filter", "value"),
    Input("search-category", "value"),
    Input("patent-year-slider", "value"),
    Input("carnegie-filter", "value"),
)
def update_patents_table(click, patents_map_filter, categories, patent_year_range, carnegie):

    if not click or "points" not in click:
        return "Select a university on the patents map", []

    hover_html = click["points"][0]["text"]
    first_line = hover_html.split("<br>")[0]
    clean_univ = strip_html(first_line)
    univ_key = normalize_univ(clean_univ)

    ymin, ymax = patent_year_range
    rows = []

    # Carnegie filter
    if carnegie != "All":
        df_car = PatentYears[PatentYears["University"] == univ_key]
        if df_car.empty or df_car["Carnegie"].iloc[0] != carnegie:
            return f"Selected University: {clean_univ}", []

    df_univ = PatentYears[PatentYears["University"] == univ_key]

    if patents_map_filter:
        df_univ = df_univ[df_univ["Category"].isin(patents_map_filter)]
    if categories:
        df_univ = df_univ[df_univ["Category"].isin(categories)]

    df_univ = df_univ[(df_univ["year"] >= ymin) & (df_univ["year"] <= ymax)]

    for _, row in df_univ.iterrows():
        key = (row["University"], row["Category"])
        top5 = Top5PatentsDict.get(key, [])

        for patent in top5:
            rows.append({
                "title": patent.get("patent_title", ""),              # REAL TITLE
                "type": "patent",
                "category": row["Category"],
                "Seed": row["Seed"],
                "year": patent.get("year", row["year"]),
                "work_id": patent["patent_id"]         # REAL PATENT ID
            })

    if not rows:
        return f"Selected University: {clean_univ}", []

    df = pd.DataFrame(rows).sort_values("year", ascending=False)
    return f"Selected University: {clean_univ}", df.to_dict("records")


# =====================================================================
# SELECTED UNIVERSITY TABLE — COMBINED MAP (FIXED TITLES)
# =====================================================================
@map.callback(
    Output("selected-university-title-combined", "children"),
    Output("university-table-combined", "data"),
    Input("combined-map", "clickData"),
    Input("combined-category-filter", "value"),
    Input("combined-patent-year-slider", "value"),
)
def update_combined_table(click, categories, patent_year_range):

    if not click or "points" not in click:
        return "Select a university on the combined map", []

    hover_html = click["points"][0]["text"]
    first_line = hover_html.split("<br>")[0]
    clean_univ = strip_html(first_line)
    univ_key = normalize_univ(clean_univ)

    tmin, tmax = patent_year_range
    rows = []

    # Papers (no year filtering)
    for (u, category), works in Top5PapersDict.items():
        if u != univ_key:
            continue
        if categories and category not in categories:
            continue
        for w in works:
            rows.append({
                "title": w["title"],
                "type": "paper",
                "category": category,
                "Seed": w.get("seed", ""),
                "year": w.get("year", ""),
                "work_id": w.get("openalex_url", "")
            })

    # Patents (year filtered)
    df_univ = PatentYears[PatentYears["University"] == univ_key]
    if categories:
        df_univ = df_univ[df_univ["Category"].isin(categories)]
    df_univ = df_univ[(df_univ["year"] >= tmin) & (df_univ["year"] <= tmax)]

    for _, row in df_univ.iterrows():
        key = (row["University"], row["Category"])
        top5 = Top5PatentsDict.get(key, [])

        for patent in top5:
            rows.append({
                "title": patent.get("patent_title", ""),              # REAL TITLE
                "type": "patent",
                "category": row["Category"],
                "Seed": row["Seed"],
                "year": patent.get("year", row["year"]),
                "work_id": patent["patent_id"]         # REAL PATENT ID
            })

    if not rows:
        return f"Selected University: {clean_univ}", []

    df = pd.DataFrame(rows).sort_values("year", ascending=False)
    return f"Selected University: {clean_univ}", df.to_dict("records")


# =====================================================================
# SEARCH — UNIFIED RESULTS TABLE (FIXED TITLES)
# =====================================================================
@map.callback(
    Output("search-results-table", "data"),
    Input("search-category", "value"),
    Input("content", "value"),
    Input("carnegie-filter", "value"),
    Input("NUniversities", "value"),
    Input("search-university", "value"),
    Input("patent-year-slider", "value"),
)
def update_search_results(categories, content_type,
                          carnegie_value, N, keyword, patent_year_range):

    df_p = PaperCounts.copy()

    tmin, tmax = patent_year_range
    df_t = PatentYears.copy()
    df_t = df_t[(df_t["year"] >= tmin) & (df_t["year"] <= tmax)]

    if categories:
        df_p = df_p[df_p["Category"].isin(categories)]
        df_t = df_t[df_t["Category"].isin(categories)]

    if carnegie_value != "All":
        df_p = df_p[df_p["Carnegie"] == carnegie_value]
        df_t = df_t[df_t["Carnegie"] == carnegie_value]

    if content_type == "papers":
        df_t = df_t.iloc[0:0]
    elif content_type == "patents":
        df_p = df_p.iloc[0:0]

    merged = pd.merge(
        df_p,
        df_t,
        on=["University", "Category", "Carnegie", "Latitude", "Longitude", "State"],
        how="outer",
        suffixes=("_papers", "_patents")
    )

    merged["works_count"] = merged["works_count"].fillna(0).astype(int)
    merged["patent_count"] = merged["patent_count"].fillna(0).astype(int)

    rows = []

    for _, row in merged.iterrows():

        univ = row["University"]
        category = row["Category"]
        state = row["State"]

        # Papers
        if row["works_count"] > 0 and content_type in ("papers", "both"):
            key = (univ, category)
            if key in Top5PapersDict:
                for w in Top5PapersDict[key]:

                    rows.append({
                        "University": univ.title(),
                        "State": state,
                        "Carnegie": row["Carnegie"],
                        "Category": category,
                        "Seed": w.get("seed", ""),
                        "works_count": row["works_count"],
                        "us_patents_count": row["patent_count"],
                        "type": "paper",
                        "title": w["title"],
                        "year": w.get("year", ""),
                        "cited_by_count": w.get("cited_by_count", ""),
                        "ID": w.get("openalex_url", "")
                    })

        # Patents (REAL TITLES)
        if row["patent_count"] > 0 and content_type in ("patents", "both"):

            key = (univ, category)
            top5 = Top5PatentsDict.get(key, [])

            for patent in top5:
                rows.append({
                    "University": univ.title(),
                    "State": state,
                    "Carnegie": row["Carnegie"],
                    "Category": category,
                    "Seed": patent.get("seed", row.get("Seed_patents", "")),
                    "works_count": row["works_count"],
                    "us_patents_count": row["patent_count"],
                    "type": "patent",
                    "title": patent.get("patent_title", ""),              # REAL TITLE
                    "year": patent.get("year", row.get("year", "")),
                    "cited_by_count": "",
                    "ID": patent["patent_id"]              # REAL PATENT ID
                })

    if not rows:
        return []

    df_rows = pd.DataFrame(rows).drop_duplicates()

    if keyword:
        kw = keyword.lower()
        df_rows = df_rows[
            df_rows["University"].str.lower().str.contains(kw, na=False)
            | df_rows["Category"].str.lower().str.contains(kw, na=False)
            | df_rows["Seed"].str.lower().str.contains(kw, na=False)
            | df_rows["title"].str.lower().str.contains(kw, na=False)
            | df_rows["State"].str.lower().str.contains(kw, na=False)
            | df_rows["ID"].str.lower().str.contains(kw, na=False)
        ]

    return df_rows.head(N).to_dict("records")

# =====================================================================
# UNIVERSITY OUTPUT OVER TIME — PATENTS ONLY
# =====================================================================
@map.callback(
    Output("patent-university-graphs", "children"),
    Input("patent-regionselect", "value"),
    Input("patent-NUniversities", "value"),
    Input("patent-USearch", "value")
)
def update_patent_graphs(region, num_unis, usearch):

    if region is None:
        region = "All Regions"

    df = PatentYears.copy()

    if usearch:
        df = df[
            df["University"].str.contains(usearch, case=False, na=False)
            | df["State"].str.contains(usearch, case=False, na=False)
        ]

    region_unis = df[df["State"].isin(regions[region])]["University"].unique()
    df = df[df["University"].isin(region_unis)]

    if df.empty:
        return [html.Div("No data available for selected filters.")]

    agg = (
        df.groupby(["University", "Category", "year"])["patent_count"]
          .sum()
          .reset_index(name="count")
    )

    latest_year = agg["year"].max()

    year_totals = (
        agg[agg["year"] == latest_year]
        .groupby("University")["count"]
        .sum()
        .sort_values(ascending=False)
    )

    ranking = year_totals.head(num_unis).index.tolist()

    df_top = agg[agg["University"].isin(ranking)]

    graphs = []
    for uni in ranking:
        df_uni = df_top[df_top["University"] == uni]

        fig = px.line(
            df_uni,
            x="year",
            y="count",
            color="Category",
            markers=True,
            title=uni.title(),
        )

        fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
        graphs.append(html.Div([dcc.Graph(figure=fig)], style={"marginBottom": "40px"}))

    return graphs
    
# ---------------------------------------------------------
# RUN APP
# ---------------------------------------------------------

if __name__ == "__main__":
    map.run(debug=True, port=8045)
