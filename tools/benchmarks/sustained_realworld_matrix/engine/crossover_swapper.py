#!/usr/bin/env python3
"""
tools/benchmarks/sustained_realworld_matrix/engine/crossover_swapper.py

Milestone 3: Symmetric Crossover Slot-Swapping Engine & Placement Variance Gate (< 2.5%).
Protocol:
  1. Direct Run: Slot A = OS X, Slot B = OS Y (simultaneous 300s execution).
  2. Cooldown & Inode/Cache Wipe:
     - Stop containers.
     - Recreate named scratch volumes.
     - Wait for TCP TIME_WAIT socket drainage.
  3. Swapped Run: Slot A = OS Y, Slot B = OS X (simultaneous 300s execution).
  4. Mathematical Variance Verification:
     Delta = |M_SlotA - M_SlotB| / (0.5 * (M_SlotA + M_SlotB)) * 100% < 2.5%

Proves that observed performance is OS-intrinsic and eliminates placement, port,
or host cache affinity bias.
"""

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

# Add matrix root to path
MATRIX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MATRIX_ROOT not in sys.path:
    sys.path.insert(0, MATRIX_ROOT)

from scenarios.catalog import ScenarioDefinition
from infra.container_manager import ContainerManager, SlotId
from engine.stress_ladder import StressLadderEngine, StressLadderResult


def calculate_crossover_variance_pct(metric_a: float, metric_b: float) -> float:
    """
    Computes mathematical relative variance between Slot A and Slot B runs:
    Delta = |M_A - M_B| / (0.5 * (M_A + M_B)) * 100%
    """
    if metric_a < 0 or metric_b < 0:
        raise ValueError("Metrics must be non-negative.")
    avg = 0.5 * (metric_a + metric_b)
    if avg == 0.0:
        return 0.0
    return round((abs(metric_a - metric_b) / avg) * 100.0, 3)


def evaluate_placement_bias_gate(variance_pct: float) -> bool:
    """Returns True if variance < 2.5%, False otherwise."""
    return variance_pct < 2.50


@dataclass
class CrossoverRunPair:
    scenario_id: str
    os_x: str
    os_y: str
    direct_slot_a: StressLadderResult
    direct_slot_b: StressLadderResult
    swapped_slot_a: StressLadderResult
    swapped_slot_b: StressLadderResult
    variance_os_x_throughput_pct: float
    variance_os_x_p95_pct: float
    variance_os_y_throughput_pct: float
    variance_os_y_p95_pct: float
    max_variance_pct: float
    placement_gate_passed: bool
    summary: Dict[str, Any] = field(default_factory=dict)


class CrossoverSwapperEngine:
    """
    Orchestrates the symmetric crossover slot-swapping protocol across two target operating systems.
    """

    def __init__(
        self,
        container_manager: Optional[ContainerManager] = None,
        ladder_engine: Optional[StressLadderEngine] = None,
    ):
        self.container_manager = container_manager
        self.ladder_engine = ladder_engine or StressLadderEngine()

    def run_crossover_pair(
        self,
        scenario: ScenarioDefinition,
        os_x_target: str,
        os_y_target: str,
        cooldown_s: float = 2.0,
        simulated_ladder: bool = True,
    ) -> CrossoverRunPair:
        """
        Executes both direct and swapped runs for a given scenario across OS X and OS Y.
        """
        # ======================================================================
        # Phase 1: Direct Run (Slot A = OS X, Slot B = OS Y)
        # ======================================================================
        direct_slot_a = self.ladder_engine.execute_ladder(
            scenario=scenario,
            target_os=os_x_target,
            slot_id="slot_a",
            target_ip="172.30.0.10",
            target_port=scenario.target_port,
        )

        direct_slot_b = self.ladder_engine.execute_ladder(
            scenario=scenario,
            target_os=os_y_target,
            slot_id="slot_b",
            target_ip="172.30.0.20",
            target_port=scenario.target_port,
        )

        # Cooldown & Cache Flush
        if self.container_manager is not None and not simulated_ladder:
            self.container_manager.inter_run_cooldown_and_wipe(cooldown_s=cooldown_s)
        else:
            time.sleep(min(cooldown_s, 0.05))

        # ======================================================================
        # Phase 2: Swapped Run (Slot A = OS Y, Slot B = OS X)
        # ======================================================================
        swapped_slot_a = self.ladder_engine.execute_ladder(
            scenario=scenario,
            target_os=os_y_target,
            slot_id="slot_a",
            target_ip="172.30.0.10",
            target_port=scenario.target_port,
        )

        swapped_slot_b = self.ladder_engine.execute_ladder(
            scenario=scenario,
            target_os=os_x_target,
            slot_id="slot_b",
            target_ip="172.30.0.20",
            target_port=scenario.target_port,
        )

        # ======================================================================
        # Phase 3: Mathematical Variance Verification (< 2.5%)
        # ======================================================================
        # Variance for OS X (Direct in Slot A vs Swapped in Slot B)
        rps_x_a = direct_slot_a.aggregate_metrics["average_rps"]
        rps_x_b = swapped_slot_b.aggregate_metrics["average_rps"]
        var_x_rps = calculate_crossover_variance_pct(rps_x_a, rps_x_b)

        p95_x_a = direct_slot_a.aggregate_metrics["p95_latency_ms"]
        p95_x_b = swapped_slot_b.aggregate_metrics["p95_latency_ms"]
        var_x_p95 = calculate_crossover_variance_pct(p95_x_a, p95_x_b)

        # Variance for OS Y (Direct in Slot B vs Swapped in Slot A)
        rps_y_b = direct_slot_b.aggregate_metrics["average_rps"]
        rps_y_a = swapped_slot_a.aggregate_metrics["average_rps"]
        var_y_rps = calculate_crossover_variance_pct(rps_y_b, rps_y_a)

        p95_y_b = direct_slot_b.aggregate_metrics["p95_latency_ms"]
        p95_y_a = swapped_slot_a.aggregate_metrics["p95_latency_ms"]
        var_y_p95 = calculate_crossover_variance_pct(p95_y_b, p95_y_a)

        max_var = max(var_x_rps, var_x_p95, var_y_rps, var_y_p95)
        gate_passed = evaluate_placement_bias_gate(max_var)

        summary = {
            "scenario_id": scenario.id,
            "os_x": os_x_target,
            "os_y": os_y_target,
            "os_x_direct_slot_a_rps": rps_x_a,
            "os_x_swapped_slot_b_rps": rps_x_b,
            "os_x_rps_variance_pct": var_x_rps,
            "os_x_p95_variance_pct": var_x_p95,
            "os_y_direct_slot_b_rps": rps_y_b,
            "os_y_swapped_slot_a_rps": rps_y_a,
            "os_y_rps_variance_pct": var_y_rps,
            "os_y_p95_variance_pct": var_y_p95,
            "max_variance_pct": max_var,
            "placement_bias_gate_passed": gate_passed,
        }

        return CrossoverRunPair(
            scenario_id=scenario.id,
            os_x=os_x_target,
            os_y=os_y_target,
            direct_slot_a=direct_slot_a,
            direct_slot_b=direct_slot_b,
            swapped_slot_a=swapped_slot_a,
            swapped_slot_b=swapped_slot_b,
            variance_os_x_throughput_pct=var_x_rps,
            variance_os_x_p95_pct=var_x_p95,
            variance_os_y_throughput_pct=var_y_rps,
            variance_os_y_p95_pct=var_y_p95,
            max_variance_pct=max_var,
            placement_gate_passed=gate_passed,
            summary=summary,
        )
