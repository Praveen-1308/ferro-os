"""
tools/benchmarks/sustained_realworld_matrix/scenarios/catalog.py
Master Scenario Catalog Registry: Canonical registry of 65 production scenarios across 6 categories.
Guarantees 0% synthetic / zero simulated delay compliance.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple


class ScenarioCategory(str, Enum):
    WEB_MICROSERVICES = "web_microservices"
    DATABASES_STATE_ENGINES = "databases_state_engines"
    HIGH_CHURN_IO_MEDIA = "high_churn_io_media"
    QUEUEING_TELEMETRY_STREAMING = "queueing_telemetry_streaming"
    INCIDENT_RADAR_FAULTS = "incident_radar_faults"
    DEADZONE_HARDWARE_EXTREMES = "deadzone_hardware_extremes"


@dataclass(frozen=True)
class ScenarioDefinition:
    id: str
    name: str
    category: ScenarioCategory
    protocol: str
    target_port: int
    sla_p95_ms: float
    description: str = ""
    driver_type: str = ""
    driver_script: str = ""
    driver_args: List[str] = field(default_factory=list)
    server_cmd: List[str] = field(default_factory=list)
    expected_exit_code: int = 0
    verification_keys: List[str] = field(
        default_factory=lambda: ["zero_synthetic", "sla_p95", "rss_stability"]
    )


# Category Quotas
CATEGORY_QUOTAS: Dict[ScenarioCategory, int] = {
    ScenarioCategory.WEB_MICROSERVICES: 15,
    ScenarioCategory.DATABASES_STATE_ENGINES: 12,
    ScenarioCategory.HIGH_CHURN_IO_MEDIA: 10,
    ScenarioCategory.QUEUEING_TELEMETRY_STREAMING: 10,
    ScenarioCategory.INCIDENT_RADAR_FAULTS: 10,
    ScenarioCategory.DEADZONE_HARDWARE_EXTREMES: 8,
}
TOTAL_CATALOG_COUNT: int = sum(CATEGORY_QUOTAS.values())  # 65


def build_master_catalog() -> Dict[str, ScenarioDefinition]:
    """Compiles the master registry from all 6 operational scenario modules."""
    catalog: Dict[str, ScenarioDefinition] = {}

    from scenarios.web_microservices import WEB_SCENARIOS
    from scenarios.databases import DATABASE_SCENARIOS
    from scenarios.high_churn_io import IO_SCENARIOS
    from scenarios.queueing_streaming import QUEUEING_SCENARIOS
    from scenarios.incident_faults import INCIDENT_FAULTS_SCENARIOS
    from scenarios.deadzone_extremes import DEADZONE_EXTREMES_SCENARIOS

    for s in WEB_SCENARIOS.values():
        catalog[s.id] = ScenarioDefinition(
            id=s.id,
            name=s.name,
            category=ScenarioCategory.WEB_MICROSERVICES,
            protocol=s.protocol,
            target_port=s.target_port,
            sla_p95_ms=s.sla_p95_ms,
            description=s.description,
            driver_type=s.driver_type,
            driver_script=s.driver_script,
            driver_args=list(s.driver_args),
            server_cmd=list(s.server_cmd),
            verification_keys=list(s.verification_keys),
        )

    for s in DATABASE_SCENARIOS.values():
        catalog[s.id] = ScenarioDefinition(
            id=s.id,
            name=s.name,
            category=ScenarioCategory.DATABASES_STATE_ENGINES,
            protocol=s.protocol,
            target_port=s.target_port,
            sla_p95_ms=s.sla_p95_ms,
            description=s.description,
            driver_type=s.driver_type,
            driver_script=s.driver_script,
            driver_args=list(s.driver_args),
            server_cmd=list(s.server_cmd),
            verification_keys=list(s.verification_keys),
        )

    for s in IO_SCENARIOS.values():
        catalog[s.id] = ScenarioDefinition(
            id=s.id,
            name=s.name,
            category=ScenarioCategory.HIGH_CHURN_IO_MEDIA,
            protocol=s.protocol,
            target_port=s.target_port,
            sla_p95_ms=s.sla_p95_ms,
            description=s.description,
            driver_type=s.driver_type,
            driver_script=s.driver_script,
            driver_args=list(s.driver_args),
            server_cmd=list(s.server_cmd),
            verification_keys=list(s.verification_keys),
        )

    for s in QUEUEING_SCENARIOS.values():
        catalog[s.id] = ScenarioDefinition(
            id=s.id,
            name=s.name,
            category=ScenarioCategory.QUEUEING_TELEMETRY_STREAMING,
            protocol=s.protocol,
            target_port=s.target_port,
            sla_p95_ms=s.sla_p95_ms,
            description=s.description,
            driver_type=s.driver_type,
            driver_script=s.driver_script,
            driver_args=list(s.driver_args),
            server_cmd=list(s.server_cmd),
            verification_keys=list(s.verification_keys),
        )

    for s in INCIDENT_FAULTS_SCENARIOS.values():
        catalog[s.id] = ScenarioDefinition(
            id=s.id,
            name=s.name,
            category=ScenarioCategory.INCIDENT_RADAR_FAULTS,
            protocol=s.protocol,
            target_port=s.target_port,
            sla_p95_ms=s.sla_p95_ms,
            description=s.description,
            driver_type=s.driver_type,
            driver_script=s.driver_script,
            driver_args=list(s.driver_args),
            server_cmd=list(s.server_cmd),
            expected_exit_code=s.expected_exit_code,
            verification_keys=list(s.verification_keys),
        )

    for s in DEADZONE_EXTREMES_SCENARIOS.values():
        catalog[s.id] = ScenarioDefinition(
            id=s.id,
            name=s.name,
            category=ScenarioCategory.DEADZONE_HARDWARE_EXTREMES,
            protocol=s.protocol,
            target_port=s.target_port,
            sla_p95_ms=s.sla_p95_ms,
            description=s.description,
            driver_type=s.driver_type,
            driver_script=s.driver_script,
            driver_args=list(s.driver_args),
            server_cmd=list(s.server_cmd),
            expected_exit_code=s.expected_exit_code,
            verification_keys=list(s.verification_keys),
        )

    return catalog


def get_scenario(scenario_id: str) -> Optional[ScenarioDefinition]:
    """Retrieves a scenario definition by ID."""
    catalog = build_master_catalog()
    return catalog.get(scenario_id)


def list_scenarios(category: Optional[Any] = None) -> List[ScenarioDefinition]:
    """Lists scenario definitions, optionally filtered by category."""
    catalog = build_master_catalog()
    if category is None:
        return list(catalog.values())

    cat_val = category.value if isinstance(category, ScenarioCategory) else str(category)
    return [s for s in catalog.values() if s.category.value == cat_val or s.category == category]


def validate_catalog() -> Tuple[bool, Optional[str]]:
    """Validates full catalog completeness, quotas, ports, and SLA bounds."""
    catalog = build_master_catalog()
    if len(catalog) != TOTAL_CATALOG_COUNT:
        return False, f"Total scenario count mismatch: {len(catalog)} != {TOTAL_CATALOG_COUNT}"

    for cat, quota in CATEGORY_QUOTAS.items():
        actual = len([s for s in catalog.values() if s.category == cat])
        if actual != quota:
            return False, f"Category {cat.value} quota mismatch: {actual} != {quota}"

    for s in catalog.values():
        if s.target_port < 0 or s.target_port > 65535:
            return False, f"Scenario {s.id} invalid port: {s.target_port}"
        if s.sla_p95_ms <= 0.0 or s.sla_p95_ms > 1000.0:
            return False, f"Scenario {s.id} invalid SLA: {s.sla_p95_ms}"
        if not s.protocol.strip():
            return False, f"Scenario {s.id} missing protocol"

    return True, None


def build_reference_scenario_catalog() -> Dict[str, Dict[str, Any]]:
    """Returns dictionary schema compatible with tests/test_harness.py."""
    catalog = build_master_catalog()
    return {
        s.id: {
            "id": s.id,
            "name": s.name,
            "category": s.category.value if isinstance(s.category, ScenarioCategory) else s.category,
            "protocol": s.protocol,
            "target_port": s.target_port,
            "sla_p95_ms": s.sla_p95_ms,
        }
        for s in catalog.values()
    }
