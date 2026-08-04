import logging
from typing import Dict, Any
from src.agents.base import BaseAgent
from src.state import GraphState

logger = logging.getLogger(__name__)

# Hardcoded reference mapping based on the drawing legend sheets (Piping and Instrument Line/Tag standards)
STANDARD_LEGENDS = {
    "line_tag_format": {
        "pattern": "SIZE-SERVICE-SYSTEM-SEQUENCE-CLASS-INSULATION",
        "description": "Pipe size (inches) - Product Service - System No - Sequence No - Classification - Insulation Class",
        "examples": ["8\"-PV-26-9035-FC11S-08", "1\"-DC-26-9053-GC11S-00"]
    },
    "service_codes": {
        "PV": "Process hydrocarbon gas/vapor",
        "PL": "Process hydrocarbon liquid",
        "DC": "Drain closed",
        "DO": "Drain open",
        "WC": "Cooling medium / water",
        "AI": "Instrument Air",
        "GI": "Nitrogen / Inert Gas",
        "LO": "Lube oil",
        "VF": "Vent to flare"
    },
    "valve_types": {
        "GATE": ["Gate Valve", "GV"],
        "GLOBE": ["Globe Valve", "GLV"],
        "BALL": ["Ball Valve", "BV"],
        "NEEDLE": ["Needle Valve", "NV"],
        "CHECK": ["Check Valve", "CV"],
        "BUTTERFLY": ["Butterfly Valve", "BFV"],
        "DIAPHRAGM": ["Diaphragm Valve", "DV"],
        "PSV": ["Pressure Safety Valve", "Relief Valve"],
        "CONTROL": ["Control Valve"]
    },
    "instrument_types": {
        "PIT": "Pressure Indicator Transmitter",
        "PI": "Pressure Indicator",
        "TIT": "Temperature Indicator Transmitter",
        "TI": "Temperature Indicator",
        "FE": "Flow Element / Orifice",
        "FI": "Flow Indicator",
        "PDIT": "Pressure Differential Indicator Transmitter",
        "PDI": "Pressure Differential Indicator",
        "PSE": "Pressure Safety Element",
        "XV": "Shutdown/Solenoid Valve"
    },
    "equipment_classes": {
        "KA": "Compressor (e.g. 26-KA-901 or 26-KA-902)",
        "C": "Column / Tower",
        "V": "Vessel / Drum",
        "HA": "Heat Exchanger",
        "G": "Pump",
        "KZ": "Packages / Skids (e.g. 26-KZ-901 / 26-KZ-902)"
    },
    "validation_rules": [
        "Valve size must match the size code of its associated pipeline.",
        "Equipment tags must begin with the system prefix (e.g. 26-).",
        "All manual valves must indicate normal operating position (e.g., LO, LC, CSO, CSC).",
        "All instruments must be linked to a physical line or equipment host."
    ]
}

class ContextLoaderAgent(BaseAgent):
    """
    Agent responsible for loading legend sheets, client specs, and coding standards.
    """
    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Context Loader Agent...")
        
        # In a production environment, this agent might load text or tables from a vector database
        # or OCR on a legend PDF. Here we load our reference standard.
        loaded_context = {
            "legends": STANDARD_LEGENDS,
            "loaded_files": state.get("raw_documents", [])[1:]  # Treat secondary documents as references/legends
        }
        
        return {
            "engineering_context": loaded_context,
            "revision_history": state.get("revision_history", []) + [{"action": "Loaded engineering standards and legend sheets"}]
        }
