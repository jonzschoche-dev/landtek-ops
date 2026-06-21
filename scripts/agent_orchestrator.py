#!/usr/bin/env python3
"""agent_orchestrator.py — Unified orchestration for all 8 agents.

Manages: scheduling, triggering, observability, error handling, operator notifications.
"""
import os
import sys
import subprocess
import json
from datetime import datetime, timedelta
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Agent registry: name, script, trigger, cadence
AGENTS = {
    "discovery": {
        "script": "agent_discovery.py",
        "trigger": "schedule",
        "cadence_hours": 6,
        "wave": 1,
        "critical": True
    },
    "execution_tracking": {
        "script": "agent_execution_tracking.py",
        "trigger": "schedule",
        "cadence_hours": 12,
        "wave": 1,
        "critical": True
    },
    "deadline_orchestration": {
        "script": "agent_deadline_orchestration.py",
        "trigger": "schedule",
        "cadence_hours": 24,  # daily at 00:01 UTC
        "wave": 1,
        "critical": True
    },
    "narrative_generation": {
        "script": "agent_narrative_generation.py",
        "trigger": "on_demand",
        "wave": 1,
        "critical": False
    },
    "cascade_verification": {
        "script": "agent_cascade_verification.py",
        "trigger": "event",
        "wave": 2,
        "critical": False
    },
    "opponent_modeling": {
        "script": "agent_opponent_modeling.py",
        "trigger": "schedule",
        "cadence_hours": 168,  # weekly
        "wave": 2,
        "critical": False
    },
    "cost_outcome": {
        "script": "agent_cost_outcome.py",
        "trigger": "event",
        "wave": 2,
        "critical": False
    },
    "settlement_valuation": {
        "script": "agent_settlement_valuation.py",
        "trigger": "on_demand",
        "wave": 2,
        "critical": False
    }
}

class AgentOrchestrator:
    """Unified orchestration for all agents."""
    
    def __init__(self):
        self.conn = psycopg2.connect(DSN)
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
    
    def get_constitution(self):
        """Read current Constitution."""
        try:
            with open('/root/landtek/SYSTEM_CONSTITUTION.md', 'r') as f:
                return f.read()
        except FileNotFoundError:
            return None
    
    def should_run(self, agent_name, agent_config):
        """Check if agent should run now."""
        # For now, all scheduled agents run (production: check last_run_at)
        return agent_config.get("trigger") in ["schedule", "on_demand"]
    
    def run_agent(self, agent_name, agent_config):
        """Execute an agent."""
        script_path = os.path.join(self.script_dir, agent_config["script"])
        
        if not os.path.exists(script_path):
            print(f"  ⚠️  Script not found: {script_path}")
            return None
        
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=300  # 5 min timeout
            )
            
            if result.returncode == 0:
                print(f"  ✓ {agent_name} completed")
                return result.stdout
            else:
                print(f"  ✗ {agent_name} failed: {result.stderr}")
                return None
        
        except subprocess.TimeoutExpired:
            print(f"  ✗ {agent_name} timed out")
            return None
        except Exception as e:
            print(f"  ✗ {agent_name} error: {e}")
            return None
    
    def update_agent_status(self, agent_name, success):
        """Update agent_status table."""
        self.cur.execute("""
            INSERT INTO agent_status (agent_name, last_run_at, is_active)
            VALUES (%s, NOW(), TRUE)
            ON CONFLICT (agent_name) DO UPDATE
            SET last_run_at = NOW(),
                last_successful_run_at = CASE WHEN %s THEN NOW() ELSE last_successful_run_at END,
                error_count = CASE WHEN %s THEN 0 ELSE error_count + 1 END;
        """, (agent_name, success, success))
        self.conn.commit()
    
    def notify_operator(self, message, severity="info"):
        """Notify operator via Telegram (integration point)."""
        # TODO: wire to Leo / Telegram
        print(f"  [NOTIFY {severity.upper()}] {message}")
    
    def run_wave(self, wave_num):
        """Run all agents in a wave."""
        print(f"\n{'='*60}")
        print(f"AGENT WAVE {wave_num} (Started {datetime.now().isoformat()})")
        print(f"{'='*60}\n")
        
        constitution = self.get_constitution()
        if not constitution:
            print("⚠️  Constitution not found; agents will operate with limited grounding.")
        
        for agent_name, agent_config in AGENTS.items():
            if agent_config["wave"] != wave_num:
                continue
            
            if not agent_config.get("wave"):
                continue
            
            print(f"[{agent_name}]")
            
            if self.should_run(agent_name, agent_config):
                result = self.run_agent(agent_name, agent_config)
                success = result is not None
                self.update_agent_status(agent_name, success)
                
                if success and agent_config.get("critical"):
                    self.notify_operator(
                        f"Agent {agent_name} completed",
                        severity="info"
                    )
            else:
                print(f"  (skip: not yet scheduled)")
        
        print(f"\nWave {wave_num} complete.\n")
    
    def run_all(self):
        """Run all waves in order."""
        self.run_wave(1)  # Critical for Aug 12
        self.run_wave(2)  # Enterprise hardening

if __name__ == "__main__":
    orchestrator = AgentOrchestrator()
    
    if len(sys.argv) > 1 and sys.argv[1] == "wave1":
        orchestrator.run_wave(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "wave2":
        orchestrator.run_wave(2)
    else:
        orchestrator.run_all()

