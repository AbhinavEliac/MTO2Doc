import logging
from typing import Dict, Any, List
from src.agents.base import BaseAgent
from src.state import GraphState

logger = logging.getLogger(__name__)

class ValidationAgent(BaseAgent):
    """
    Validation Agent evaluates consistency rules, orphan symbols,
    tag naming conventions, and size compliance.
    """
    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Validation Agent...")
        
        graph = state.get("engineering_graph")
        if not graph:
            raise ValueError("No compiled EngineeringGraph found in state for validation.")

        reports = []

        # Rule 1: Check for duplicate tags across all components
        all_tags = []
        for eq in graph.equipment:
            all_tags.append((eq.tag, "Equipment"))
        for line in graph.lines:
            all_tags.append((line.tag, "Line"))
        for inst in graph.instruments:
            all_tags.append((inst.tag, "Instrument"))
        for valve in graph.valves:
            all_tags.append((valve.tag, "Valve"))
            
        seen_tags = {}
        for tag, comp_type in all_tags:
            if tag in seen_tags:
                reports.append({
                    "rule_id": "VAL-001",
                    "severity": "ERROR",
                    "target_tag": tag,
                    "message": f"Duplicate tag '{tag}' detected across {seen_tags[tag]} and {comp_type}."
                })
            seen_tags[tag] = comp_type

        # Rule 2: Verify Valve sizes against their associated pipeline sizes
        for valve in graph.valves:
            if valve.line_tag:
                # Find associated line
                line_obj = next((l for l in graph.lines if l.tag == valve.line_tag), None)
                if line_obj:
                    # Clean size strings for comparison (e.g. remove quotes)
                    clean_valve_size = str(valve.size).replace('"', '').strip()
                    clean_line_size = str(line_obj.size).replace('"', '').strip()
                    
                    if clean_valve_size != clean_line_size:
                        reports.append({
                            "rule_id": "VAL-002",
                            "severity": "ERROR",
                            "target_tag": valve.tag,
                            "message": f"Valve size ({valve.size}) mismatch with host line size ({line_obj.size}) on '{valve.line_tag}'."
                        })
            else:
                reports.append({
                    "rule_id": "VAL-003",
                    "severity": "WARNING",
                    "target_tag": valve.tag,
                    "message": f"Orphan valve: Valve '{valve.tag}' is not associated with any pipeline."
                })

        # Rule 3: Check for orphan instruments (no connection/relationships)
        for inst in graph.instruments:
            has_relation = False
            for rel in graph.relationships:
                if rel.source == inst.tag or rel.target == inst.tag:
                    has_relation = True
                    break
            if not has_relation:
                reports.append({
                    "rule_id": "VAL-004",
                    "severity": "WARNING",
                    "target_tag": inst.tag,
                    "message": f"Orphan instrument: Instrument '{inst.tag}' has no logical connections to lines or equipment."
                })

        # Rule 4: Verify equipment naming convention format (must start with system prefix, e.g., '26-')
        for eq in graph.equipment:
            if not eq.tag.startswith("26-") and not eq.tag.startswith("40-") and not eq.tag.startswith("63-"):
                reports.append({
                    "rule_id": "VAL-005",
                    "severity": "WARNING",
                    "target_tag": eq.tag,
                    "message": f"Equipment tag '{eq.tag}' does not start with a standard system code prefix."
                })

        logger.info(f"Validation complete. Identified {len(reports)} inconsistencies.")
        
        return {
            "validation_reports": reports,
            "revision_history": state.get("revision_history", []) + [{"action": "Validation checks run", "issues_found": len(reports)}]
        }
