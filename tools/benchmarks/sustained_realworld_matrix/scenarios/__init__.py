"""
tools/benchmarks/sustained_realworld_matrix/scenarios/__init__.py
Sustained Real-World Empirical Benchmark Matrix — 65 Production Scenarios Catalog.
"""

from scenarios.catalog import (
    ScenarioCategory,
    ScenarioDefinition,
    build_master_catalog,
    get_scenario,
    list_scenarios,
    validate_catalog,
    build_reference_scenario_catalog,
    CATEGORY_QUOTAS,
    TOTAL_CATALOG_COUNT,
)

__all__ = [
    "ScenarioCategory",
    "ScenarioDefinition",
    "build_master_catalog",
    "get_scenario",
    "list_scenarios",
    "validate_catalog",
    "build_reference_scenario_catalog",
    "CATEGORY_QUOTAS",
    "TOTAL_CATALOG_COUNT",
]
