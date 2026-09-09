"""Recipe files both ways: Feature objects, links, and compliance to JSON (``write_recipe``) and back (``load_recipe``)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mloda.provider import FeatureGroup
from mloda.user import Feature, Index, JoinSpec, Link, load_features_from_config
from pydantic import ValidationError

# Registration side effect: a fresh process loading a recipe must resolve GovDataFeature and the readers.
from ..feature_groups import destatis, govdata  # noqa: F401
from ..feature_groups.destatis.locator import DestatisLocator
from ..feature_groups.govdata.core.locator import DEFAULT_CKAN_BASE, GovDataLocator
from .model import Compliance, JoinSide, LinkSpec, Recipe, RecipeError, error_summary

# mloda's DefaultOptionKeys.in_features is a str enum equal to this; the loader stores it in Options.context.
IN_FEATURES = "in_features"
# Feature attributes with no field in the mloda feature config. domain and compute_framework may also
# arrive through options (mloda reads those keys itself); then they round-trip with the options.
_UNSUPPORTED = (("data_type", None), ("index", None), ("domain", "domain"), ("compute_frameworks", "compute_framework"))


@dataclass(frozen=True)
class LoadedRecipe:
    """What ``load_recipe`` returns: pass ``features`` and ``set(links)`` to ``mloda.run_all``."""

    features: list[Feature | str]
    links: list[Link]
    compliance: Compliance


def build_recipe(features: Iterable[Feature | str], compliance: Compliance, links: Iterable[Link] = ()) -> Recipe:
    """Feature objects (or names), links, and compliance to a validated ``Recipe``; feature-level links are hoisted."""
    feature_list = list(features)
    all_links = list(links)
    for feature in feature_list:
        if isinstance(feature, Feature) and feature.link is not None and not _contains(all_links, feature.link):
            all_links.append(feature.link)
    items = [
        feature if isinstance(feature, str) else _feature_item(feature, position)
        for position, feature in enumerate(feature_list)
    ]
    try:
        specs = [_link_spec(link, position) for position, link in enumerate(all_links)]
        return Recipe(features=items, links=specs, compliance=compliance)
    except ValidationError as exc:
        raise RecipeError(error_summary(exc)) from None


def recipe_to_json(recipe: Recipe) -> str:
    """Stable, human-readable JSON; the feature array is written exactly as the model holds it."""
    document = {
        "features": recipe.features,
        "links": [spec.model_dump(mode="json", exclude_none=True) for spec in recipe.links],
        "compliance": recipe.compliance.model_dump(mode="json", exclude_none=True),
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def write_recipe(
    path: str | Path, features: Iterable[Feature | str], compliance: Compliance, links: Iterable[Link] = ()
) -> Path:
    target = Path(path)
    target.write_text(recipe_to_json(build_recipe(features, compliance, links)), encoding="utf-8")
    return target


def parse_recipe(text: str, label: str = "recipe") -> LoadedRecipe:
    """Validate recipe JSON and turn it into mloda objects; ``label`` names the source in errors."""
    try:
        recipe = Recipe.model_validate_json(text)
    except ValidationError as exc:
        raise RecipeError(f"{label}: {error_summary(exc)}") from None
    return realize_recipe(recipe, label)


def load_recipe(path: str | Path) -> LoadedRecipe:
    source = Path(path)
    return parse_recipe(source.read_text(encoding="utf-8"), label=str(source))


def realize_recipe(recipe: Recipe, label: str = "recipe") -> LoadedRecipe:
    """A validated ``Recipe`` to mloda objects. Only the feature array reaches mloda's config loader."""
    try:
        features = load_features_from_config(json.dumps(recipe.features), format="json")
    except (TypeError, ValueError) as exc:
        raise RecipeError(f"{label}: mloda rejected the feature array: {exc}") from exc
    links = [_build_link(spec, f"{label}: links[{position}]") for position, spec in enumerate(recipe.links)]
    return LoadedRecipe(features=features, links=links, compliance=recipe.compliance)


def _feature_item(feature: Feature, position: int) -> dict[str, Any]:
    where = f"features[{position}] ({feature.name})"
    options = feature.options
    for attribute, option_key in _UNSUPPORTED:
        if getattr(feature, attribute) is not None and (option_key is None or option_key not in options.group):
            raise RecipeError(
                f"{where}: Feature.{attribute} has no field in the mloda feature config; "
                "a recipe carries name, options, in_features, feature_group, and propagate_context_keys"
            )
    group = _json_value(options.group, f"{where}.options")
    context = dict(options.context)
    in_features = context.pop(IN_FEATURES, None)
    context_json = _json_value(context, f"{where}.context_options")
    item: dict[str, Any] = {"name": str(feature.name)}
    if in_features is not None:
        item[IN_FEATURES] = _in_feature_names(in_features, where)
    if context_json:
        if group:
            item["group_options"] = group
        item["context_options"] = context_json
        if options.propagate_context_keys:
            item["propagate_context_keys"] = sorted(options.propagate_context_keys)
    elif group:
        item["options"] = group
    scope = feature.feature_group_scope
    if scope is not None:
        item["feature_group"] = scope if isinstance(scope, str) else scope.get_class_name()
    return item


def _in_feature_names(value: Any, where: str) -> list[str]:
    names = [name.strip() for name in value.split(",")] if isinstance(value, str) else list(value)
    if not all(isinstance(name, str) and name for name in names):
        raise RecipeError(f"{where}: in_features must be feature names; a nested Feature has no config form")
    return sorted(names)


def _json_value(value: Any, where: str) -> Any:
    """The JSON-safe subset of option values; a locator becomes its string or dict form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, DestatisLocator):
        return {key: item for key, item in value.to_dict().items() if item is not None}
    if isinstance(value, GovDataLocator):
        if value.ckan_base != DEFAULT_CKAN_BASE or value.resource_index != 0:
            raise RecipeError(
                f"{where}: a GovDataLocator with a non-default ckan_base or resource_index has no config form"
            )
        return value.describe()
    if isinstance(value, (set, frozenset)):
        return sorted((_json_value(item, where) for item in value), key=str)
    if isinstance(value, (list, tuple)):
        return [_json_value(item, where) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RecipeError(f"{where}: option key {key!r} is not a string")
            result[key] = _json_value(item, f"{where}.{key}")
        return result
    raise RecipeError(
        f"{where}: {type(value).__name__} values are not JSON-safe; pass strings, numbers, lists, dicts, or a locator"
    )


def _link_spec(link: Link, position: int) -> LinkSpec:
    where = f"links[{position}]"
    if link.asof_config is not None:
        raise RecipeError(f"{where}: asof joins have no recipe form")
    return LinkSpec.model_validate(
        {
            "join": link.jointype.value,
            "left": _join_side(link.left_feature_group, link.left_index, link.left_discriminator, f"{where}.left"),
            "right": _join_side(link.right_feature_group, link.right_index, link.right_discriminator, f"{where}.right"),
        }
    )


def _join_side(feature_group: type[Any], index: Index, discriminator: dict[str, Any] | None, where: str) -> JoinSide:
    return JoinSide(
        feature_group=feature_group.get_class_name(),
        index=list(index.index),
        discriminator=None if discriminator is None else _json_value(discriminator, f"{where}.discriminator"),
    )


def _build_link(spec: LinkSpec, where: str) -> Link:
    left = JoinSpec(_resolve_feature_group(spec.left.feature_group, f"{where}.left"), Index(tuple(spec.left.index)))
    right = JoinSpec(_resolve_feature_group(spec.right.feature_group, f"{where}.right"), Index(tuple(spec.right.index)))
    return Link(
        spec.join, left, right, left_discriminator=spec.left.discriminator, right_discriminator=spec.right.discriminator
    )


def _resolve_feature_group(name: str, where: str) -> type[FeatureGroup]:
    matches = {cls for cls in _subclasses(FeatureGroup) if cls.get_class_name() == name}
    if not matches:
        raise RecipeError(
            f"{where}: no FeatureGroup named {name!r} is loaded; import its module before loading the recipe"
        )
    if len(matches) > 1:
        modules = sorted(f"{cls.__module__}.{cls.__qualname__}" for cls in matches)
        raise RecipeError(f"{where}: FeatureGroup name {name!r} is ambiguous: {modules}")
    return matches.pop()


def _subclasses(cls: type[FeatureGroup]) -> Iterator[type[FeatureGroup]]:
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)


def _contains(links: list[Link], link: Link) -> bool:
    # Link equality ignores discriminators, so two nodes of one class joined twice stay distinct here.
    return any(
        known == link
        and known.left_discriminator == link.left_discriminator
        and known.right_discriminator == link.right_discriminator
        for known in links
    )
