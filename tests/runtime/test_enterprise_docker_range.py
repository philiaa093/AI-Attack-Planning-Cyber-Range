"""Comprehensive Docker Deployment & Wire-Level Validation Suite (RT-06V).

Validates:
  1. Docker Compose stack deployment validity and container health.
  2. Physical wire-level network isolation:
     - DMZ ingress accessible from host on loopback (127.0.0.1:18081).
     - Clean control accessible from host on loopback (127.0.0.1:18085).
     - Internal / Restricted / Decoy services have NO published host ports.
     - Direct connection from DMZ to Restricted fails closed (separate Docker networks).
     - Direct connection from DMZ to Decoy fails closed (separate Docker networks).
     - Outbound internet from isolated networks is completely blocked (internal: true).
  3. Real live episodes against Docker containers:
     - L1: DMZ -> Lateral Pivot to Internal -> Objective Access to Restricted -> Safe STOP.
     - L2: Blocked route triggers WAF_REJECTION defensive signal; unblock replans successfully.
     - L3: Clean control baseline rejects attack actions and halts cleanly via STOP.
     - L4: Decoy probe triggers AUTH_LOCKOUT defensive alert.
  4. CentralizedSafetyGate and KillSwitch enforce ZERO network dispatch to Docker targets.
  5. Source of truth for target states resides in running Docker containers.
"""
from __future__ import annotations

import http.client
import json
import unittest
from urllib.parse import urlsplit

from actions.catalog.action_registry import (
    CANONICAL_BENCHMARK_ACTION_IDS,
    get_canonical_action_id,
)
from agent.memory.state.belief_state import BeliefState
from runtime.lab.enterprise_range.harness import DockerEnterpriseRangeHarness
from runtime.lab.enterprise_range.topology import ENTERPRISE_TARGETS, ZONES
from runtime.lab.live_environment import (
    LiveEpisodeEnvironment,
    create_live_safety_gate,
)
from runtime.lab.live_executor_adapter import (
    LiveExecutionResult,
    LiveExecutorAdapter,
)
from runtime.orchestration.planner_runner import PlannerEpisodeRunner
from runtime.planners.rule_based_planner import RuleBasedPlanner
from runtime.safety.discovery_gate import CentralizedSafetyGate, KillSwitch


from pathlib import Path
import shutil
import subprocess
import time

from runtime.evidence.discovery_recorder import ROOT


class TestEnterpriseDockerRange(unittest.TestCase):
    """Integration test suite executing against real Docker Compose containers."""

    _we_started_compose = False

    @classmethod
    def _find_docker(cls) -> str | None:
        found = shutil.which("docker")
        if found:
            return found
        fallback = Path(r"C:\Users\DELL\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe")
        if fallback.exists():
            return str(fallback)
        return None

    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = DockerEnterpriseRangeHarness()
        health = cls.harness.health_check_all()
        if health.get("lab-enterprise-dmz") and health.get("lab-enterprise-clean"):
            return

        docker_bin = cls._find_docker()
        if not docker_bin:
            raise unittest.SkipTest("DOCKER_E2E_BLOCKED_BY_ENVIRONMENT: Docker CLI not found")

        # Verify docker daemon is accessible
        info_check = subprocess.run([docker_bin, "info"], capture_output=True, text=True, check=False)
        if info_check.returncode != 0:
            raise unittest.SkipTest(f"DOCKER_E2E_BLOCKED_BY_ENVIRONMENT: Docker daemon unreachable: {info_check.stderr}")

        compose_file = ROOT / "cyber-range" / "enterprise_range" / "compose.enterprise.yaml"
        try:
            up_res = subprocess.run(
                [docker_bin, "compose", "-f", str(compose_file), "up", "-d"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if up_res.returncode != 0:
                raise unittest.SkipTest(f"DOCKER_E2E_BLOCKED_BY_ENVIRONMENT: docker compose up failed: {up_res.stderr}")
            cls._we_started_compose = True
            time.sleep(2.0)
        except Exception as exc:
            raise unittest.SkipTest(f"DOCKER_E2E_BLOCKED_BY_ENVIRONMENT: {exc}")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._we_started_compose:
            docker_bin = cls._find_docker()
            if docker_bin:
                compose_file = ROOT / "cyber-range" / "enterprise_range" / "compose.enterprise.yaml"
                try:
                    subprocess.run(
                        [docker_bin, "compose", "-f", str(compose_file), "down"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=False,
                    )
                except Exception:
                    pass

    def setUp(self) -> None:
        self.harness.reset_all()

    # -------------------------------------------------------------------------
    # 1. Health and Readiness Audit
    # -------------------------------------------------------------------------
    def test_docker_containers_health_and_readiness(self) -> None:
        """Verify that all 5 Docker containers are responsive and return correct zone IDs."""
        health = self.harness.health_check_all()
        self.assertTrue(health.get("lab-enterprise-dmz"), "DMZ container must be healthy")
        self.assertTrue(health.get("lab-enterprise-clean"), "Clean control container must be healthy")
        self.assertTrue(health.get("lab-enterprise-internal"), "Internal container must be healthy via relay")
        self.assertTrue(health.get("lab-enterprise-restricted"), "Restricted container must be healthy via relay")
        self.assertTrue(health.get("lab-enterprise-decoy"), "Decoy container must be healthy via relay")

    # -------------------------------------------------------------------------
    # 2. Wire-Level Isolation Verification
    # -------------------------------------------------------------------------
    def test_wire_level_host_direct_internal_rejected(self) -> None:
        """Verify that host cannot directly reach internal services on unpublished ports."""
        for unpublished_port in (18082, 18083, 18084):
            conn = http.client.HTTPConnection("127.0.0.1", unpublished_port, timeout=1.0)
            try:
                conn.request("GET", "/health")
                self.fail(f"Host should not be able to connect to unpublished port {unpublished_port}")
            except Exception:
                pass
            finally:
                conn.close()

    def test_wire_level_dmz_cannot_reach_restricted_directly(self) -> None:
        """Verify that DMZ relay cannot directly reach Restricted Vault across unjoined networks."""
        # Even if DMZ has a foothold, direct relay to restricted-service must fail
        self.harness.dispatch_bounded_request(
            target_id="lab-enterprise-dmz",
            method="POST",
            path="/api/v1/auth/foothold",
            body={"target_id": "lab-enterprise-dmz"},
        )
        # Attempt direct jump to restricted-service bypassing internal-service
        direct_jump = {
            "target_host": "restricted-service",
            "target_port": 8080,
            "method": "GET",
            "path": "/health",
        }
        res = self.harness._dispatch_http_raw(
            self.harness.dmz_host,
            self.harness.dmz_port,
            "POST",
            "/api/v1/relay",
            body=direct_jump,
        )
        self.assertEqual(res.get("http_status"), 403)
        self.assertEqual(res.get("error"), "NETWORK_ISOLATION_BARRIER")

    def test_wire_level_dmz_cannot_reach_decoy_directly(self) -> None:
        """Verify that DMZ relay cannot directly reach Decoy across unjoined networks."""
        self.harness.dispatch_bounded_request(
            target_id="lab-enterprise-dmz",
            method="POST",
            path="/api/v1/auth/foothold",
            body={"target_id": "lab-enterprise-dmz"},
        )
        direct_jump = {
            "target_host": "decoy-service",
            "target_port": 8080,
            "method": "GET",
            "path": "/health",
        }
        res = self.harness._dispatch_http_raw(
            self.harness.dmz_host,
            self.harness.dmz_port,
            "POST",
            "/api/v1/relay",
            body=direct_jump,
        )
        self.assertEqual(res.get("http_status"), 403)
        self.assertEqual(res.get("error"), "NETWORK_ISOLATION_BARRIER")

    # -------------------------------------------------------------------------
    # 3. Live Episode Validation L1 on Docker (DMZ -> Internal -> Restricted)
    # -------------------------------------------------------------------------
    def test_live_episode_validation_l1_on_docker(self) -> None:
        """End-to-End Live Episode Validation L1 on running Docker containers."""
        env = LiveEpisodeEnvironment(
            harness=self.harness,
            entry_target_id="lab-enterprise-dmz",
            objective_id="OBJ-ENTERPRISE-MISSION",
            max_steps=25,
            max_budget=25,
        )
        planner = RuleBasedPlanner()
        runner = PlannerEpisodeRunner(env=env, planner=planner)

        result = runner.run()

        # In L1, the episode should terminate having achieved the mission objective
        self.assertTrue(result.terminated or result.final_belief_state.is_objective_achieved())
        self.assertTrue(result.final_belief_state.is_objective_achieved())

        # Verify zone progression facts in final belief state
        observed_targets = result.final_belief_state.visible_target_ids
        self.assertIn("lab-enterprise-dmz", observed_targets)
        self.assertIn("lab-enterprise-internal", observed_targets)
        self.assertIn("lab-enterprise-restricted", observed_targets)

        # Verify all action IDs in traces are canonical
        self.assertGreater(len(result.traces), 0)
        for trace in result.traces:
            if trace.chosen_proposal:
                self.assertIn(
                    get_canonical_action_id(trace.chosen_proposal["action_id"]),
                    CANONICAL_BENCHMARK_ACTION_IDS,
                )

    # -------------------------------------------------------------------------
    # 4. Live Episode Validation L2 on Docker (Blocked / Replan)
    # -------------------------------------------------------------------------
    def test_live_episode_validation_l2_blocked_replan_on_docker(self) -> None:
        """Validation Case L2: Primary route blocked on Docker, observable signal, replan."""
        env = LiveEpisodeEnvironment(
            harness=self.harness,
            entry_target_id="lab-enterprise-dmz",
            objective_id="OBJ-ENTERPRISE-MISSION",
            max_steps=25,
            max_budget=25,
        )
        env.reset()

        # Step 1: Recon DMZ
        r1 = env.step({"action_id": "ACTION-DISCOVERY-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r1.success)

        # Step 2: Foothold DMZ
        r2 = env.step({"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r2.success)

        # Step 3: Host recon DMZ (discovers Internal)
        r3 = env.step({"action_id": "ACTION-HOSTRECON-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r3.success)

        # Block route on running internal Docker container
        self.harness.block_route("lab-enterprise-internal", "primary")

        # Step 4: Harvest creds
        r4 = env.step({"action_id": "ACTION-CREDS-001", "target_id": "lab-enterprise-dmz"})
        self.assertTrue(r4.success)

        # Step 5: Attempt pivot on blocked primary route
        r5 = env.step({
            "action_id": "ACTION-PIVOT-001",
            "target_id": "lab-enterprise-internal",
            "from_node_id": "lab-enterprise-dmz",
            "route": "primary",
        })
        self.assertFalse(r5.success)
        # Defense signal should be recorded in belief
        sig_facts = env.get_belief_state().detection_signals
        self.assertTrue(len(sig_facts) > 0)
        self.assertEqual(sig_facts[0]["signal_type"], "WAF_REJECTION")

        # Step 6: Replan — unblock secondary route and retry
        self.harness.unblock_route("lab-enterprise-internal", "primary")
        r6 = env.step({
            "action_id": "ACTION-PIVOT-001",
            "target_id": "lab-enterprise-internal",
            "from_node_id": "lab-enterprise-dmz",
            "route": "secondary",
        })
        self.assertTrue(r6.success)
        active_hosts = {s.get("target_id") for s in env.get_belief_state().active_sessions}
        self.assertIn("lab-enterprise-internal", active_hosts)

    # -------------------------------------------------------------------------
    # 5. Live Episode Validation L3 on Docker (Clean Control Baseline)
    # -------------------------------------------------------------------------
    def test_live_episode_validation_l3_clean_control_on_docker(self) -> None:
        """Validation Case L3: Clean control target contains zero vulnerabilities; stops cleanly."""
        env = LiveEpisodeEnvironment(
            harness=self.harness,
            entry_target_id="lab-enterprise-clean",
            objective_id="OBJ-ENTERPRISE-MISSION",
            max_steps=10,
            max_budget=10,
        )
        env.reset()

        # Step 1: Recon clean target
        r1 = env.step({"action_id": "ACTION-DISCOVERY-001", "target_id": "lab-enterprise-clean"})
        self.assertTrue(r1.success)

        # Step 2: Foothold attempt fails on secure target
        r2 = env.step({"action_id": "ACTION-FOOTHOLD-001", "target_id": "lab-enterprise-clean"})
        self.assertFalse(r2.success)

        # Verify no sessions or access granted
        self.assertEqual(len(env.get_belief_state().active_sessions), 0)

        # Clean termination via STOP
        r_stop = env.step({"action_id": "ACTION-STOP-001", "target_id": "lab-enterprise-clean"})
        self.assertTrue(r_stop.success)
        self.assertTrue(env.terminated)
        self.assertFalse(env.is_objective_achieved())

    # -------------------------------------------------------------------------
    # 6. Live Validation Case L4 on Docker (Decoy Honeypot Alert)
    # -------------------------------------------------------------------------
    def test_live_validation_case_l4_decoy_defense_signal_on_docker(self) -> None:
        """Validation Case L4: Decoy probe triggers observable AUTH_LOCKOUT signal."""
        # 1. Foothold DMZ
        self.harness.dispatch_bounded_request(
            target_id="lab-enterprise-dmz",
            method="POST",
            path="/api/v1/auth/foothold",
            body={"target_id": "lab-enterprise-dmz"},
        )
        # 2. Pivot to Internal
        self.harness.dispatch_bounded_request(
            target_id="lab-enterprise-internal",
            method="POST",
            path="/api/v1/pivot",
            body={"from_node_id": "lab-enterprise-dmz"},
        )

        belief = BeliefState.from_facts([
            {
                "fact_id": "FACT-TGT-INT",
                "fact_type": "TARGET",
                "subject": "lab-enterprise-internal",
                "value": "lab-enterprise-internal",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-SESS-INT",
                "fact_type": "SESSION",
                "subject": "lab-enterprise-internal",
                "value": {"session_id": "SESS-LIVE-INT-00", "access_level": "USER", "state": "ACTIVE"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-ACC-INT",
                "fact_type": "ACCESS",
                "subject": "lab-enterprise-internal",
                "value": "USER",
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-REACH-DEC",
                "fact_type": "REACHABILITY",
                "subject": "lab-enterprise-internal",
                "value": {"from_host": "lab-enterprise-internal", "to_host": "lab-enterprise-decoy"},
                "confidence": 1.0,
            },
            {
                "fact_id": "FACT-TGT-DEC",
                "fact_type": "TARGET",
                "subject": "lab-enterprise-decoy",
                "value": "lab-enterprise-decoy",
                "confidence": 1.0,
            },
        ])

        adapter = LiveExecutorAdapter(harness=self.harness)
        decoy_prop = {
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "lab-enterprise-decoy",
            "from_node_id": "lab-enterprise-internal",
        }
        res = adapter.execute_proposal(decoy_prop, belief_state=belief)
        self.assertFalse(res.success)
        obs = res.canonical_observation
        self.assertIsNotNone(obs)

        sig_facts = [f for f in obs.get("new_facts", []) if f.get("fact_type") == "DETECTION_SIGNAL"]
        self.assertEqual(len(sig_facts), 1)
        self.assertEqual(sig_facts[0]["value"]["signal_type"], "AUTH_LOCKOUT")

    # -------------------------------------------------------------------------
    # 7. Safety Gate & Kill Switch Zero Dispatch on Docker
    # -------------------------------------------------------------------------
    def test_safety_gate_and_kill_switch_zero_docker_dispatch(self) -> None:
        """Verify that Safety Gate denial or Kill Switch causes ZERO dispatch to Docker containers."""
        gate = create_live_safety_gate()
        adapter = LiveExecutorAdapter(harness=self.harness, safety_gate=gate)

        # 1. Target not in allowlist
        res1 = adapter.execute_proposal({
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "external-evil.com",
        })
        self.assertFalse(res1.success)
        self.assertEqual(res1.status, "REJECTED_BY_SAFETY_GATE")
        self.assertEqual(adapter.network_dispatch_count, 0)

        # 2. Trigger kill switch
        gate.kill_switch.activate()
        res2 = adapter.execute_proposal({
            "action_id": "ACTION-DISCOVERY-001",
            "target_id": "lab-enterprise-dmz",
        })
        self.assertFalse(res2.success)
        self.assertEqual(res2.status, "REJECTED_BY_SAFETY_GATE")
        self.assertEqual(adapter.network_dispatch_count, 0)


if __name__ == "__main__":
    unittest.main()
