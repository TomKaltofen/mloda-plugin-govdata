"""Marimo demo: Berlin Wahl 2026, die wartende Zelle.

One declarative recipe connects Berlin's open voting data: three past elections
(AGH 2023, EU 2024, BT 2025) at Wahlbezirk level, demographics per district,
and the official 2023-on-2026-geometry baseline. After the election on
20 September 2026, one config slot holds the 2026 export URL, and the same
recipe reads the new results.

Run with: marimo edit demos/berlin_wahl_2026_demo.py (needs network access;
install the "demo" extra).
"""

import marimo

__generated_with = "0.23.11"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md("""
    # Berlin Wahl 2026: die wartende Zelle

    On **20 September 2026** Berlin elected its 20. Abgeordnetenhaus. This
    notebook connects the open voting data before and after that day
    through one declarative mloda recipe. At the end, one config slot holds
    the 2026 export URL, and the same recipe reads the new results. A new
    election is configuration, not code.

    Part of the Prototype Fund project mloda-plugin-govdata (FKZ 16IS26S11).
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    The Wahl zum 20. Abgeordnetenhaus von Berlin took place on **20 September 2026**.
    Everything below runs on published open data, the 2026 results included.
    """)
    return


@app.cell
def _():
    import altair as alt
    import pandas as pd

    from mloda.user import Feature, mloda
    from mloda_plugin_govdata.feature_groups.govdata import (
        OPTION_WAHL_HEADER_ROWS,
        OPTION_WAHL_LABEL_COLUMNS,
        OPTION_WAHL_SKIPROWS,
        OPTION_WAHL_VALUE_TYPE,
        BundeswahlleiterinReader,
        search_datasets,
    )
    from mloda_plugin_govdata.feature_groups.govdata.core.client import build_client, request_with_retry

    return (
        BundeswahlleiterinReader,
        Feature,
        OPTION_WAHL_HEADER_ROWS,
        OPTION_WAHL_LABEL_COLUMNS,
        OPTION_WAHL_SKIPROWS,
        OPTION_WAHL_VALUE_TYPE,
        alt,
        build_client,
        mloda,
        pd,
        request_with_retry,
        search_datasets,
    )


@app.cell
def _(mo):
    mo.md("""
    ## 1. Discover: what Berlin publishes

    Berlin's election datasets are harvested from daten.berlin.de into
    GovData, so the plugin's CKAN search finds them.
    """)
    return


@app.cell
def _(mo):
    wahl_query = mo.ui.text(value="wahlen berlin wahlbezirken", label="GovData search", full_width=True)
    wahl_query
    return (wahl_query,)


@app.cell
def _(build_client, pd, search_datasets, wahl_query):
    with build_client() as _client:
        _hits = list(search_datasets(_client, wahl_query.value, max_results=10))
    wahl_datasets = pd.DataFrame({"name": [d.name for d in _hits], "title": [d.title for d in _hits]})
    wahl_datasets
    return


@app.cell
def _(mo):
    mo.md("""
    An honest footnote: the statistics office relaunched its website in July
    2026, and the harvested CSV resource URLs behind these catalog entries
    currently return the new site's homepage instead of data. Open data needs
    consumers that notice. The cells below therefore read the
    wahlen-berlin.de exports directly, which are alive and stable.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2. One recipe, three elections, one city

    The Landeswahlleiterin publishes every election in one export schema:
    a single header row, twelve label columns, then vote counts and
    percentages per party column. So one geometry, passed as feature
    options, reads all of them; only the URL changes.
    """)
    return


@app.cell
def _(
    BundeswahlleiterinReader,
    OPTION_WAHL_HEADER_ROWS,
    OPTION_WAHL_LABEL_COLUMNS,
    OPTION_WAHL_SKIPROWS,
    OPTION_WAHL_VALUE_TYPE,
):
    BERLIN_EXPORTS = {
        "AGH 2023": "https://www.wahlen-berlin.de/wahlen/BE2023/AFSPRAES/agh/Datenexport_AGH2023_Zweitstimme_W_BE.csv",
        "EU 2024": "https://www.wahlen-berlin.de/wahlen/EU2024/AFSPRAES/Datenexport_EUROPAWAHL2024_Stimme_W_BE.csv",
        "BT 2025": (
            "https://www.wahlen-berlin.de/wahlen/BU2025/afspraes/Datenexport_BUNDESTAGSWAHL2025_Zweitstimme_W_BE.csv"
        ),
    }

    def berlin_options(url: str) -> dict[str, object]:
        # One geometry for every Datenexport file: no preamble, one header row,
        # 12 label columns (Adresse..Zeit), float values (counts and percentages).
        return {
            BundeswahlleiterinReader.__name__: url,
            OPTION_WAHL_SKIPROWS: 0,
            OPTION_WAHL_HEADER_ROWS: 1,
            OPTION_WAHL_LABEL_COLUMNS: 12,
            OPTION_WAHL_VALUE_TYPE: "float",
        }

    # The exports label parties by ballot position (P01, P02, ...). Decoded by
    # matching city-wide sums against the official results; see the proof cell.
    PARTY_LEGEND = {
        "AGH 2023": {"P01": "SPD", "P02": "CDU", "P03": "GRÜNE", "P04": "Die Linke", "P05": "AfD", "P06": "FDP"},
        "EU 2024": {
            "P01": "GRÜNE",
            "P02": "CDU",
            "P03": "SPD",
            "P04": "Die Linke",
            "P05": "AfD",
            "P07": "FDP",
            "P28": "BSW",
        },
        "BT 2025": {
            "P01": "SPD",
            "P02": "GRÜNE",
            "P03": "CDU",
            "P04": "Die Linke",
            "P05": "AfD",
            "P06": "FDP",
            "P16": "BSW",
        },
    }
    return BERLIN_EXPORTS, PARTY_LEGEND, berlin_options


@app.cell
def _(BERLIN_EXPORTS, Feature, PARTY_LEGEND, berlin_options, mloda, pd):
    _frames = []
    for _wahl, _url in BERLIN_EXPORTS.items():
        _opts = berlin_options(_url)
        _wanted = ["Bezirksname", "OstWest", "Gueltig", *PARTY_LEGEND[_wahl]]
        _table = mloda.run_all(
            [Feature(_column, options=_opts) for _column in _wanted],
            compute_frameworks=["PyArrowTable"],
        )[0]
        _frame = _table.to_pandas().rename(columns=PARTY_LEGEND[_wahl])
        _frame["Wahl"] = _wahl
        _frames.append(_frame)
    elections = pd.concat(_frames, ignore_index=True)
    elections
    return (elections,)


@app.cell
def _(mo):
    mo.md("""
    ### Proof of the party legend

    The exports never name the parties. City-wide sums recover them: each
    column's share matches exactly one line of the official result. AGH 2023
    P01 sums to 279,017 votes and P03 to 278,964, which is the famous 53-vote
    gap between SPD and GRÜNE.
    """)
    return


@app.cell
def _(elections):
    party_cols = [_c for _c in elections.columns if _c not in ("Bezirksname", "OstWest", "Gueltig", "Wahl")]
    _sums = elections.groupby("Wahl")[[*party_cols, "Gueltig"]].sum(min_count=1)  # a party that did not run stays empty
    wahl_shares = (100 * _sums[party_cols].div(_sums["Gueltig"], axis=0)).round(1)
    wahl_shares
    return (party_cols,)


@app.cell
def _(elections, mo):
    bezirk_pick = mo.ui.dropdown(options=sorted(elections["Bezirksname"].unique()), value="Mitte", label="Bezirk")
    bezirk_pick
    return (bezirk_pick,)


@app.cell
def _(alt, bezirk_pick, elections, party_cols):
    _bezirk = elections[elections["Bezirksname"] == bezirk_pick.value]
    _sums = _bezirk.groupby("Wahl")[[*party_cols, "Gueltig"]].sum(min_count=1)
    _long = (
        (100 * _sums[party_cols].div(_sums["Gueltig"], axis=0))
        .reset_index()
        .melt(id_vars=["Wahl"], var_name="Partei", value_name="Anteil")
        .dropna()
    )
    alt.Chart(_long, title=f"{bezirk_pick.value}: the same Kiez, three different parliaments").mark_bar().encode(
        x=alt.X("Partei:N", title=None, sort="-y"),
        xOffset="Wahl:N",
        y=alt.Y("Anteil:Q", title="Stimmenanteil %"),
        color="Wahl:N",
        tooltip=["Partei", "Wahl", alt.Tooltip("Anteil:Q", format=".1f")],
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3. Kiez-Kompass: demographics meet votes

    The statistics office publishes Strukturdaten for the 2026 Wahlbezirke
    and, crucially, the 2023 results recalculated onto the 2026 boundaries
    (the official baseline for the 2026 swing). Joined on the district
    key, demographics meet votes. The fact that every export still carries
    an Ost/West field is itself part of the story: color by it and the two
    clouds separate.
    """)
    return


@app.cell
def _(build_client, pd, request_with_retry):
    import io

    _struktur_url = (
        "https://download.statistik-berlin-brandenburg.de/aa56eddd2ea25921/1dd6f94397c4/DL_BE_AH2026_Strukturdaten.xlsx"
    )
    _baseline_url = (
        "https://download.statistik-berlin-brandenburg.de/eddea71cdf4e6f2b/291e0923b0a7/DL_BE_AGH2026_AGH2023.xlsx"
    )
    with build_client() as _client:
        _struktur_bytes = request_with_retry(_client, "GET", _struktur_url).content
        _baseline_bytes = request_with_retry(_client, "GET", _baseline_url).content
    strukturdaten = pd.read_excel(io.BytesIO(_struktur_bytes), sheet_name="Strukturdaten")
    baseline_2023 = pd.read_excel(io.BytesIO(_baseline_bytes), sheet_name="2023_Zweitstimme")
    kiez = strukturdaten.merge(baseline_2023, on="Adresse", suffixes=("", "_wahl"))
    kiez = kiez[kiez["Wahlbezirksart"] == "W"].copy()  # Urnenwahlbezirke: residents live there
    kiez["Wahlbeteiligung"] = 100 * kiez["Wählende"] / kiez["Wahlberechtigte insgesamt"]
    kiez.head(10)
    return (kiez,)


@app.cell
def _(mo):
    kompass_x = mo.ui.dropdown(
        options=[
            "Einwohner 65 und älter Prozent",
            "Einwohner 18 - 65 Prozent",
            "Ausländer Prozent",
            "EU-Bürger Prozent",
        ],
        value="Einwohner 65 und älter Prozent",
        label="Strukturmerkmal (x)",
    )
    kompass_y = mo.ui.dropdown(
        options=[
            "CDU in Prozent",
            "SPD in Prozent",
            "GRÜNE in Prozent",
            "Die Linke in Prozent",
            "AfD in Prozent",
            "FDP in Prozent",
            "Wahlbeteiligung",
        ],
        value="GRÜNE in Prozent",
        label="Wahlergebnis 2023 (y)",
    )
    mo.hstack([kompass_x, kompass_y])
    return kompass_x, kompass_y


@app.cell
def _(alt, kiez, kompass_x, kompass_y):
    alt.Chart(kiez, title="Jeder Punkt ist ein Wahlbezirk (2026er Zuschnitt)").mark_circle(opacity=0.45).encode(
        x=alt.X(f"{kompass_x.value}:Q"),
        y=alt.Y(f"{kompass_y.value}:Q"),
        color=alt.Color("OstWest:N", title="Ost/West"),
        tooltip=["Adresse", "Bezirksname", alt.Tooltip(f"{kompass_y.value}:Q", format=".1f")],
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. Die Wahlnacht im Zeitraffer

    The EU 2024 export carries genuine election-night count timestamps: the
    first Wahlbezirk reported at 18:27, the last before midnight. Replaying
    the running shares shows the result stabilizing within an hour. (The AGH
    2023 and BT 2025 timestamps reflect multi-day final data entry instead.)
    """)
    return


@app.cell
def _(BERLIN_EXPORTS, Feature, PARTY_LEGEND, alt, berlin_options, mloda, pd):
    _opts = berlin_options(BERLIN_EXPORTS["EU 2024"])
    _parties = PARTY_LEGEND["EU 2024"]
    _wanted = ["Zeit", "Gueltig", *_parties]
    _table = mloda.run_all(
        [Feature(_column, options=_opts) for _column in _wanted],
        compute_frameworks=["PyArrowTable"],
    )[0]
    _nacht = _table.to_pandas().rename(columns=_parties)
    _nacht["Uhrzeit"] = pd.to_datetime("2024-06-09 " + _nacht["Zeit"])
    _nacht = _nacht.sort_values("Uhrzeit").reset_index(drop=True)
    _cum = _nacht[[*_parties.values(), "Gueltig"]].cumsum()
    _running = 100 * _cum[list(_parties.values())].div(_cum["Gueltig"], axis=0)
    _running["Uhrzeit"] = _nacht["Uhrzeit"]
    _long = _running.melt(id_vars=["Uhrzeit"], var_name="Partei", value_name="laufender Anteil")
    alt.Chart(_long, title="EU 2024 in Berlin: laufendes Ergebnis am Wahlabend").mark_line().encode(
        x=alt.X("Uhrzeit:T", title="9. Juni 2024"),
        y=alt.Y("laufender Anteil:Q", title="Stimmenanteil % (kumuliert)"),
        color="Partei:N",
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Die wartende Zelle

    This is the cell this notebook exists for. Before 20 September 2026 it
    held `None`; afterwards the Landeswahlleiterin published the 2026 export
    at the path predicted from BE2023 and BU2025, with the same columns. The
    URL below is the only new input: no release, no change to the reader.
    """)
    return


@app.cell
def _():
    ELECTION_2026_URL = (
        "https://www.wahlen-berlin.de/wahlen/BE2026/AFSPRAES/agh/Datenexport_AGH2026_Zweitstimme_W_BE.csv"
    )
    return (ELECTION_2026_URL,)


@app.cell
def _(ELECTION_2026_URL, Feature, berlin_options, mloda, mo, pd):
    _opts = berlin_options(ELECTION_2026_URL)
    _positions = [f"P{_i:02d}" for _i in range(1, 121)]  # the 2026 export has 120 ballot columns
    _table = mloda.run_all(
        [Feature(_column, options=_opts) for _column in ["Bezirksname", "Gueltig", *_positions]],
        compute_frameworks=["PyArrowTable"],
    )[0]
    _frame = _table.to_pandas()
    _votes = _frame[_positions].sum()
    _shares = (100 * _votes[_votes > 0] / _frame["Gueltig"].sum()).round(1)
    wartende_zelle = pd.DataFrame({"Stimmzettelplatz": _shares.index, "Stimmenanteil %": _shares.values})
    mo.vstack(
        [
            mo.md(f"**AGH-Wahl 2026**: {len(_frame)} Wahlbezirke im Export."),
            wartende_zelle,
        ]
    )
    return


@app.cell
def _(mo):
    mo.md("""
    The table shows every ballot position that received votes
    (Stimmzettelplatz), not yet decoded to parties for 2026; that works the
    same way as in section 2, city-wide sums against the official result.

    Sources: Die Landeswahlleiterin für Berlin (wahlen-berlin.de) and the Amt
    für Statistik Berlin-Brandenburg.
    """)
    return


if __name__ == "__main__":
    app.run()
