"""Marimo demo: discover GovData datasets, read the three M1 example datasets, run two Destatis recipes.

Run with: marimo edit demos/govdata_demo.py (needs network access; install the
"demo" extra for marimo itself).
"""

import marimo

__generated_with = "0.14.16"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(
        """
        # mloda-plugin-govdata demo

        German open government data as mloda features: search GovData via the
        paginated CKAN API, read the three M1 example datasets (population,
        elections, environment) as typed Arrow tables, then run two shipped
        recipes over Destatis tables. Every cell below talks to the live
        endpoints; downloads are cached locally after the first run.

        Part of the Prototype Fund project mloda-plugin-govdata (FKZ 16IS26S11).
        """
    )
    return


@app.cell
def _():
    import pandas as pd

    from mloda.user import Feature, mloda
    from mloda_plugin_govdata.feature_groups.govdata import (
        BundeswahlleiterinReader,
        StuttgartPopulationReader,
        UbaAirReader,
        build_client,
        search_datasets,
        uba_measures_url,
    )

    return (
        BundeswahlleiterinReader,
        Feature,
        StuttgartPopulationReader,
        UbaAirReader,
        build_client,
        mloda,
        pd,
        search_datasets,
        uba_measures_url,
    )


@app.cell
def _(mo):
    mo.md("""## 1. Discover datasets (paginated CKAN `package_search`)""")
    return


@app.cell
def _(mo):
    query = mo.ui.text(value="einwohner stuttgart altersgruppen", label="GovData search", full_width=True)
    query
    return (query,)


@app.cell
def _(build_client, pd, query, search_datasets):
    with build_client() as _client:
        _hits = list(search_datasets(_client, query.value, max_results=10))
    hits = pd.DataFrame({"name": [d.name for d in _hits], "title": [d.title for d in _hits]})
    hits
    return


@app.cell
def _(mo):
    mo.md("""## 2. Population: Stuttgart residents by age group (GovData CSV)""")
    return


@app.cell
def _(Feature, StuttgartPopulationReader, mloda):
    _slug = "einwohner-nach-altersgruppen-und-stadtbezirken"
    _result = mloda.run_all(
        [
            Feature("Stichtag", options={StuttgartPopulationReader: _slug}),
            Feature("Stadtbezirk", options={StuttgartPopulationReader: _slug}),
            Feature("Alter in 10 Gruppen", options={StuttgartPopulationReader: _slug}),
            Feature("Einwohner", options={StuttgartPopulationReader: _slug}),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    population = _result[0].to_pandas()
    population
    return


@app.cell
def _(mo):
    mo.md("""## 3. Elections: Bundestagswahl 2025 results (`kerg.csv`, merged header)""")
    return


@app.cell
def _(BundeswahlleiterinReader, Feature, mloda):
    _kerg = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
    _result = mloda.run_all(
        [Feature("Gebiet", options={BundeswahlleiterinReader: _kerg})],
        compute_frameworks=["PyArrowTable"],
    )
    elections = _result[0].to_pandas()
    elections.head(20)
    return


@app.cell
def _(mo):
    mo.md("""## 4. Environment: hourly ozone at one station (UBA Air Data JSON)""")
    return


@app.cell
def _(Feature, UbaAirReader, mloda, uba_measures_url):
    _url = uba_measures_url(station=143, component=3, scope=2, date_from="2025-01-01", date_to="2025-01-01")
    _result = mloda.run_all(
        [
            Feature("date_start", options={UbaAirReader: _url}),
            Feature("value", options={UbaAirReader: _url}),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    environment = _result[0].to_pandas()
    environment
    return


@app.cell
def _(mo):
    mo.md("""## 5. Destatis through recipes (GENESIS-Online)""")
    return


@app.cell
def _(mo):
    mo.md(
        """
        A recipe file under `recipes/` names the features of one run, the joins, and where the data
        came from; `load_recipe` returns what `mloda.run_all` needs plus the compliance block. The
        cells below need a GENESIS-Online registration in the environment before marimo starts:
        `GENESIS_TOKEN`, or `GENESIS_USER` and `GENESIS_PASSWORD` (see `docs/credentials.md`).
        """
    )
    return


@app.cell
def _():
    from mloda_plugin_govdata.feature_groups.destatis import GENESIS_ONLINE, DestatisCredentials
    from mloda_plugin_govdata.feature_groups.govdata.core.cache import DownloadCache
    from mloda_plugin_govdata.feature_groups.harmonization import KreisRebaseFeature
    from mloda_plugin_govdata.harmonization.land_codes import check_land_names
    from mloda_plugin_govdata.harmonization.reference.download import fetch_pinned
    from mloda_plugin_govdata.harmonization.reference.sources import BBSR_KREISE
    from mloda_plugin_govdata.recipes import load_recipe

    return (
        BBSR_KREISE,
        DestatisCredentials,
        DownloadCache,
        GENESIS_ONLINE,
        KreisRebaseFeature,
        check_land_names,
        fetch_pinned,
        load_recipe,
    )


@app.cell
def _(DestatisCredentials, GENESIS_ONLINE, mo):
    mo.stop(
        DestatisCredentials.from_env(GENESIS_ONLINE) is None,
        mo.md("No GENESIS-Online credentials in the environment; the Destatis cells are skipped."),
    )
    recipes = mo.notebook_dir().parent / "recipes"

    def compliance_note(recipe):
        sources = "\n".join(
            f"- {s.attribution}, {s.license}, retrieved {s.retrieved_at:%Y-%m-%d}" for s in recipe.compliance.sources
        )
        return mo.md(f"{sources}\n\n{recipe.compliance.notes}")

    return compliance_note, recipes


@app.cell
def _(mo):
    mo.md("""### Recipe 3: population per eligible voter by Land (`12411-0010` and `kerg.csv`)""")
    return


@app.cell
def _(check_land_names, load_recipe, mloda, recipes):
    land_recipe = load_recipe(recipes / "land_population_voters.json")
    # Without the links block: mloda does not honor discriminators on a same-class link yet, so the
    # two sources come back as two frames, checked here and combined by hand below.
    _frames = mloda.run_all(land_recipe.features, compute_frameworks=["PyArrowTable"])
    population_by_land = next(t for t in _frames if "value" in t.column_names).to_pandas()
    _election = next(t for t in _frames if "Nr" in t.column_names).to_pandas()
    voters_by_land = _election[_election["gehört zu"] == "99"]  # the Land rows; Bundesgebiet has no parent
    check_land_names(
        zip(population_by_land["1_variable_attribute_code"], population_by_land["1_variable_attribute_label"])
    )
    check_land_names(zip(voters_by_land["Nr"], voters_by_land["Gebiet"]))
    return land_recipe, population_by_land, voters_by_land


@app.cell
def _(mo, population_by_land, voters_by_land):
    mo.hstack([population_by_land, voters_by_land], gap=2)
    return


@app.cell
def _(population_by_land, voters_by_land):
    _voters = "Wahlberechtigte Erststimmen Endgültig"
    per_voter = population_by_land.rename(
        columns={"1_variable_attribute_code": "Nr", "1_variable_attribute_label": "Land", "value": "Bevölkerung"}
    ).merge(voters_by_land[["Nr", _voters]].rename(columns={_voters: "Wahlberechtigte"}), on="Nr")
    per_voter["Bevölkerung je Wahlberechtigte"] = per_voter["Bevölkerung"] / per_voter["Wahlberechtigte"]
    per_voter.sort_values("Nr")[["Nr", "Land", "Bevölkerung", "Wahlberechtigte", "Bevölkerung je Wahlberechtigte"]]
    return


@app.cell
def _(compliance_note, land_recipe):
    compliance_note(land_recipe)
    return


@app.cell
def _(mo):
    mo.md("""### Recipe 1: a Kreis series re-based across the Göttingen merger (`12411-0015`, BBSR keys)""")
    return


@app.cell
def _(BBSR_KREISE, DownloadCache, KreisRebaseFeature, fetch_pinned, load_recipe, mloda, recipes):
    with DownloadCache(KreisRebaseFeature.cache_dir) as _cache:
        fetch_pinned(_cache, BBSR_KREISE, revalidate=True)  # the key file once into the cache, offline afterwards
    kreis_recipe = load_recipe(recipes / "kreis_population_rebased.json")
    rebased = mloda.run_all(kreis_recipe.features, compute_frameworks=["PyArrowTable"])[0].to_pandas()
    rebased.columns = [name.split("~")[1] for name in rebased.columns]  # destatis__bevoelkerung__kreise~key to key
    rebased[["key", "year", "value", "flag", "sources", "marker", "issues"]]
    return (kreis_recipe,)


@app.cell
def _(compliance_note, kreis_recipe):
    compliance_note(kreis_recipe)
    return


if __name__ == "__main__":
    app.run()
