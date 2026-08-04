MOCK_TEXT_ELEMENTS = [
    # Equipment List for each compressor package (26-KA-901 and 26-KA-902)
    {
        "tag": "26-KA-901", 
        "classification": "EQUIPMENT_TAG", 
        "value": "3RD STAGE HP GAS LIFT COMPRESSOR", 
        "rating": "776 kW",
        "attributes": {"design_pressure": "229 / 108.5 Barg", "design_temperature": "122 - 135 / 50 °C", "flow_rate": "19057 kg/h", "duty": "776 kW", "material": "LTCS (1.7218)"}
    },
    {
        "tag": "26-KA-901-M01", 
        "classification": "EQUIPMENT_TAG", 
        "value": "COMPRESSOR MOTOR (3RD STAGE HP GAS LIFT COMPRESSOR)", 
        "rating": None,
        "attributes": {"design_pressure": "N/A", "design_temperature": "N/A", "flow_rate": "N/A", "duty": "N/A", "material": "Copper/Steel"}
    },
    {
        "tag": "26-KA-902", 
        "classification": "EQUIPMENT_TAG", 
        "value": "3RD STAGE HP GAS EXPORT COMPRESSOR", 
        "rating": "1835 kW",
        "attributes": {"design_pressure": "FV / 286 Barg", "design_temperature": "-46 / 160 °C", "flow_rate": "62809 kg/h", "duty": "1835 kW", "material": "LTCS (1.7218)"}
    },
    {
        "tag": "26-KA-902-M01", 
        "classification": "EQUIPMENT_TAG", 
        "value": "COMPRESSOR MOTOR (3RD STAGE HP GAS EXPORT COMPRESSOR)", 
        "rating": None,
        "attributes": {"design_pressure": "N/A", "design_temperature": "N/A", "flow_rate": "N/A", "duty": "N/A", "material": "Copper/Steel"}
    },
    {
        "tag": "26-HA-911", 
        "classification": "EQUIPMENT_TAG", 
        "value": "BALANCE LINE COOLER (HEAT EXCHANGER)", 
        "rating": None,
        "attributes": {"design_pressure": "2500# Class", "design_temperature": "-29 / 150 °C", "flow_rate": "12000 kg/h", "duty": "250 kW", "material": "Duplex SS"}
    },
    {
        "tag": "26-KZ-901", 
        "classification": "EQUIPMENT_TAG", 
        "value": "COMPRESSOR AUXILIARY SKID (INCLUDES LO SYSTEM, SEAL GAS SYSTEM)", 
        "rating": None,
        "attributes": {"design_pressure": "Skid Standard", "design_temperature": "Standard", "flow_rate": "N/A", "duty": "N/A", "material": "Carbon Steel"}
    },
    {
        "tag": "26-CX-9122", 
        "classification": "EQUIPMENT_TAG", 
        "value": "OMS MODULE (COALESCER MODULE)", 
        "rating": None,
        "attributes": {"design_pressure": "300 Barg", "design_temperature": "0 / 100 °C", "flow_rate": "N/A", "duty": "N/A", "material": "SS316"}
    },
    {
        "tag": "26-CX-9011", 
        "classification": "EQUIPMENT_TAG", 
        "value": "DRY GAS SEAL FILTER MODULE", 
        "rating": None,
        "attributes": {"design_pressure": "300 Barg", "design_temperature": "0 / 100 °C", "flow_rate": "N/A", "duty": "N/A", "material": "SS316"}
    },
    
    # Piping Lines
    {"tag": "8\"-PV-26-9035-FC11S-08", "classification": "LINE_TAG", "value": "COMPRESSOR SUCTION PIPELINE", "rating": None},
    {"tag": "6\"-PV-26-9044-GC11S-38", "classification": "LINE_TAG", "value": "COMPRESSOR DISCHARGE PIPELINE", "rating": None},
    {"tag": "2\"-PL-26-9115-FC11S-00", "classification": "LINE_TAG", "value": "LUBE OIL DRAIN PIPELINE", "rating": None},
    {"tag": "1\"-DC-26-9053-GC11S-00", "classification": "LINE_TAG", "value": "COMPRESSOR CASING DRAIN PIPELINE", "rating": None},
    {"tag": "4\"-WC-26-9128-EC11S-00", "classification": "LINE_TAG", "value": "BALANCE LINE COOLER RETURN PIPELINE", "rating": None},
    {"tag": "1\"-AI-63-9006-AS20-00", "classification": "LINE_TAG", "value": "INSTRUMENT AIR SUPPLY A", "rating": None},
    {"tag": "1\"-AI-63-9007-AS20-00", "classification": "LINE_TAG", "value": "INSTRUMENT AIR SUPPLY B", "rating": None},
    {"tag": "1\"-GI-64-9002-AS20-00", "classification": "LINE_TAG", "value": "NITROGEN PURGE LINE", "rating": None},
    
    # Instruments
    {"tag": "PIT-9055", "classification": "INSTRUMENT_TAG", "value": "PRESSURE INDICATOR TRANSMITTER (SUCTION)", "rating": None},
    {"tag": "PIT-9058", "classification": "INSTRUMENT_TAG", "value": "PRESSURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "PDIT-9054", "classification": "INSTRUMENT_TAG", "value": "DIFF. PRESSURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "TIT-9057", "classification": "INSTRUMENT_TAG", "value": "TEMPERATURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "PIT-9062", "classification": "INSTRUMENT_TAG", "value": "PRESSURE INDICATOR TRANSMITTER (DISCHARGE)", "rating": None},
    {"tag": "TIT-9063", "classification": "INSTRUMENT_TAG", "value": "TEMPERATURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "TIT-9064", "classification": "INSTRUMENT_TAG", "value": "TEMPERATURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "PIT-9065", "classification": "INSTRUMENT_TAG", "value": "PRESSURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "FE-9056", "classification": "INSTRUMENT_TAG", "value": "FLOW ELEMENT (ORIFICE PLATE)", "rating": None},
    {"tag": "FI-9056", "classification": "INSTRUMENT_TAG", "value": "FLOW INDICATOR", "rating": None},
    {"tag": "TIT-9211", "classification": "INSTRUMENT_TAG", "value": "TEMPERATURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "PIT-9215", "classification": "INSTRUMENT_TAG", "value": "PRESSURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "PSE-9216", "classification": "INSTRUMENT_TAG", "value": "PRESSURE SAFETY ELEMENT (RUPTURE DISC)", "rating": None},
    {"tag": "PDIT-9757", "classification": "INSTRUMENT_TAG", "value": "DIFF. PRESSURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "PSE-9758", "classification": "INSTRUMENT_TAG", "value": "PRESSURE SAFETY ELEMENT", "rating": None},
    {"tag": "PIT-9759", "classification": "INSTRUMENT_TAG", "value": "PRESSURE INDICATOR TRANSMITTER", "rating": None},
    {"tag": "XV-9010", "classification": "INSTRUMENT_TAG", "value": "SHUTDOWN SOLENOID VALVE", "rating": None},
    {"tag": "ZSC-9010", "classification": "INSTRUMENT_TAG", "value": "LIMIT SWITCH CLOSED", "rating": None},
    {"tag": "ZSO-9010", "classification": "INSTRUMENT_TAG", "value": "LIMIT SWITCH OPEN", "rating": None},
    {"tag": "PIT-9019", "classification": "INSTRUMENT_TAG", "value": "PRESSURE INDICATOR TRANSMITTER (MOTOR TEMP)", "rating": None},
    
    # Safety Relief Valves
    {"tag": "26-PSV-9066A", "classification": "PSV_TAG", "value": "Compressor Discharge Relief - Valve A (Duty)", "rating": "257 barg", "attributes": {"inlet_size": "4\"", "outlet_size": "6\"", "inlet_spec": "300# / 2500# spec break", "relief_destination": "43-900001-001 HP Flare Header", "remarks": "Mechanical interlock with PSV-9066B; NEW"}},
    {"tag": "26-PSV-9066B", "classification": "PSV_TAG", "value": "Compressor Discharge Relief - Valve B (Standby)", "rating": "257 barg", "attributes": {"inlet_size": "4\"", "outlet_size": "6\"", "inlet_spec": "300# / 2500# spec break", "relief_destination": "43-900001-001 HP Flare Header", "remarks": "Mechanical interlock with PSV-9066A; NEW"}},
    {"tag": "26-PSV-9027A", "classification": "PSV_TAG", "value": "Compressor Discharge Relief - Valve A (KA-902 Duty)", "rating": "225.4 barg", "attributes": {"inlet_size": "4\"", "outlet_size": "4\"x1.5\"", "inlet_spec": "300# / 1500# spec break", "relief_destination": "43-900001-001 HP Flare Header", "remarks": "Mechanical interlock with PSV-9027B; NEW"}},
    {"tag": "26-PSV-9027B", "classification": "PSV_TAG", "value": "Compressor Discharge Relief - Valve B (KA-902 Standby)", "rating": "225.4 barg", "attributes": {"inlet_size": "4\"", "outlet_size": "4\"x1.5\"", "inlet_spec": "300# / 1500# spec break", "relief_destination": "43-900001-001 HP Flare Header", "remarks": "Mechanical interlock with PSV-9027A; NEW"}},
    
    # Valves
    {"tag": "26GB9178", "classification": "VALVE_TAG", "value": "MANUAL GLOBE VALVE", "rating": None},
    {"tag": "26CB9162", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9163", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9164", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9171", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9172", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9165", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9166", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9167", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9273", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9274", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26BL9077", "classification": "VALVE_TAG", "value": "BALL VALVE", "rating": None},
    {"tag": "26BL9754", "classification": "VALVE_TAG", "value": "BALL VALVE", "rating": None},
    {"tag": "26CB9711", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9712", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9271", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None},
    {"tag": "26CB9272", "classification": "VALVE_TAG", "value": "CHECK VALVE", "rating": None}
]

MOCK_SYMBOLS = [
    {"symbol_type": "COMPRESSOR", "inferred_tag": "26-KA-901", "ymin": 0.4, "xmin": 0.3, "ymax": 0.6, "xmax": 0.5},
    {"symbol_type": "MOTOR", "inferred_tag": "26-KA-901-M01", "ymin": 0.4, "xmin": 0.15, "ymax": 0.58, "xmax": 0.28},
    {"symbol_type": "COMPRESSOR", "inferred_tag": "26-KA-902", "ymin": 0.4, "xmin": 0.6, "ymax": 0.6, "xmax": 0.8},
    {"symbol_type": "MOTOR", "inferred_tag": "26-KA-902-M01", "ymin": 0.4, "xmin": 0.75, "ymax": 0.58, "xmax": 0.88},
    {"symbol_type": "COOLER", "inferred_tag": "26-HA-911", "ymin": 0.5, "xmin": 0.75, "ymax": 0.68, "xmax": 0.88},
    {"symbol_type": "SKID", "inferred_tag": "26-KZ-901", "ymin": 0.3, "xmin": 0.55, "ymax": 0.72, "xmax": 0.95},
    {"symbol_type": "COALESCER", "inferred_tag": "26-CX-9122", "ymin": 0.1, "xmin": 0.35, "ymax": 0.28, "xmax": 0.45},
    {"symbol_type": "FILTER", "inferred_tag": "26-CX-9011", "ymin": 0.1, "xmin": 0.48, "ymax": 0.28, "xmax": 0.58},
    {"symbol_type": "INST_BUBBLE", "inferred_tag": "PIT-9055", "ymin": 0.2, "xmin": 0.25, "ymax": 0.25, "xmax": 0.3},
    {"symbol_type": "INST_BUBBLE", "inferred_tag": "PIT-9019", "ymin": 0.2, "xmin": 0.65, "ymax": 0.25, "xmax": 0.7},
    {"symbol_type": "GLOBE_VALVE", "inferred_tag": "26GB9178", "ymin": 0.7, "xmin": 0.45, "ymax": 0.73, "xmax": 0.48},
    {"symbol_type": "CHECK_VALVE", "inferred_tag": "26CB9271", "ymin": 0.5, "xmin": 0.52, "ymax": 0.53, "xmax": 0.55},
    {"symbol_type": "CHECK_VALVE", "inferred_tag": "26CB9272", "ymin": 0.5, "xmin": 0.56, "ymax": 0.59, "xmax": 0.6},
    {"symbol_type": "PSV", "inferred_tag": "26-PSV-9066A", "ymin": 0.1, "xmin": 0.85, "ymax": 0.15, "xmax": 0.88},
    {"symbol_type": "PSV", "inferred_tag": "26-PSV-9066B", "ymin": 0.1, "xmin": 0.90, "ymax": 0.15, "xmax": 0.93},
    {"symbol_type": "PSV", "inferred_tag": "26-PSV-9027A", "ymin": 0.12, "xmin": 0.85, "ymax": 0.17, "xmax": 0.88},
    {"symbol_type": "PSV", "inferred_tag": "26-PSV-9027B", "ymin": 0.12, "xmin": 0.90, "ymax": 0.17, "xmax": 0.93}
]

MOCK_RELATIONS = [
    {"source_tag": "PIT-9055", "target_tag": "8\"-PV-26-9035-FC11S-08", "rel_type": "MONITORS"},
    {"source_tag": "PIT-9019", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "PIT-9058", "target_tag": "8\"-PV-26-9035-FC11S-08", "rel_type": "MONITORS"},
    {"source_tag": "PDIT-9054", "target_tag": "8\"-PV-26-9035-FC11S-08", "rel_type": "MONITORS"},
    {"source_tag": "TIT-9057", "target_tag": "8\"-PV-26-9035-FC11S-08", "rel_type": "MONITORS"},
    {"source_tag": "PIT-9062", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "MONITORS"},
    {"source_tag": "TIT-9063", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "MONITORS"},
    {"source_tag": "TIT-9064", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "MONITORS"},
    {"source_tag": "PIT-9065", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "MONITORS"},
    {"source_tag": "TIT-9211", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "PIT-9215", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "PSE-9216", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "PDIT-9757", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "PSE-9758", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "PIT-9759", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "26GB9178", "target_tag": "1\"-DC-26-9053-GC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9162", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9163", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9164", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9171", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9172", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9165", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9166", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9167", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9273", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9274", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26BL9077", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26BL9754", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9711", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9712", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9271", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26CB9272", "target_tag": "2\"-PL-26-9115-FC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "8\"-PV-26-9035-FC11S-08", "target_tag": "26-KA-901", "rel_type": "CONNECTS_TO"},
    {"source_tag": "6\"-PV-26-9044-GC11S-38", "target_tag": "26-KA-901", "rel_type": "CONNECTS_TO"},
    {"source_tag": "8\"-PV-26-9035-FC11S-08", "target_tag": "26-KA-902", "rel_type": "CONNECTS_TO"},
    {"source_tag": "6\"-PV-26-9044-GC11S-38", "target_tag": "26-KA-902", "rel_type": "CONNECTS_TO"},
    {"source_tag": "26-PSV-9066A", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26-PSV-9066B", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26-PSV-9027A", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "INSTALLED_ON"},
    {"source_tag": "26-PSV-9027B", "target_tag": "6\"-PV-26-9044-GC11S-38", "rel_type": "INSTALLED_ON"},
    {"source_tag": "FE-9056", "target_tag": "8\"-PV-26-9035-FC11S-08", "rel_type": "MONITORS"},
    {"source_tag": "FI-9056", "target_tag": "8\"-PV-26-9035-FC11S-08", "rel_type": "MONITORS"},
    {"source_tag": "XV-9010", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "INSTALLED_ON"},
    {"source_tag": "ZSC-9010", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"},
    {"source_tag": "ZSO-9010", "target_tag": "4\"-WC-26-9128-EC11S-00", "rel_type": "MONITORS"}
]
