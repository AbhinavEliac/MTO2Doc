import os
import argparse
import logging
from src.graph import create_workflow
from src.state import GraphState

# Configure logging format and level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sid_ai")

def main():
    parser = argparse.ArgumentParser(description="SID-AI: AI-Based P&ID Data Extraction & Engineering Deliverables System")
    parser.add_argument(
        "--input", 
        type=str, 
        required=True, 
        help="Path to the primary P&ID drawing file (PDF or image)"
    )
    parser.add_argument(
        "--references", 
        type=str, 
        nargs="*", 
        default=[], 
        help="Paths to optional reference legend sheets or standards documents"
    )
    parser.add_argument(
        "--max-retries", 
        type=int, 
        default=3, 
        help="Maximum focused re-extraction attempts allowed"
    )
    
    args = parser.parse_args()
    
    # 1. Verify files exist
    if not os.path.exists(args.input):
        logger.error(f"Input drawing not found at: '{args.input}'")
        return
        
    raw_docs = [args.input] + [ref for ref in args.references if os.path.exists(ref)]
    
    logger.info("Initializing P&ID Extraction Workflow...")
    
    # 2. Compile LangGraph workflow
    workflow = create_workflow()
    app = workflow.compile()
    
    # 3. Formulate initial state
    initial_state: GraphState = {
        "raw_documents": raw_docs,
        "metadata": {},
        "engineering_context": {},
        "extracted_entities": {
            "text_elements": [],
            "symbols": [],
            "relations": [],
            "geometry": {}
        },
        # Compiler will build this
        "engineering_graph": None,
        "validation_reports": [],
        "missing_entities": [],
        "revision_history": [],
        "deliverables": {},
        "re_extraction_count": 0,
        "max_re_extractions": args.max_retries,
        "re_extracted_targets": []
    }
    
    logger.info("Starting graph execution...")
    try:
        # Run graph
        final_state = app.invoke(initial_state)
        
        logger.info("\n" + "="*50 + "\nPipeline Execution Summary\n" + "="*50)
        
        # Log metadata details
        meta = final_state.get("metadata", {})
        logger.info(f"Drawing Title:    {meta.get('title', 'N/A')}")
        logger.info(f"Drawing Number:   {meta.get('drawing_number', 'N/A')}")
        logger.info(f"Revision Code:    {meta.get('revision', 'N/A')}")
        logger.info(f"Client:           {meta.get('client_name', 'N/A')}")
        logger.info(f"Page Count:       {meta.get('page_count', 0)}")
        
        # Log compiled graph quantities
        graph = final_state.get("engineering_graph")
        if graph:
            logger.info("\nCompiled Master Engineering Graph:")
            logger.info(f"- Equipment:   {len(graph.equipment)}")
            logger.info(f"- Lines:       {len(graph.lines)}")
            logger.info(f"- Instruments: {len(graph.instruments)}")
            logger.info(f"- Valves:      {len(graph.valves)}")
            logger.info(f"- Relations:   {len(graph.relationships)}")
            
        # Log validation check reports
        reports = final_state.get("validation_reports", [])
        logger.info(f"\nValidation Issues Found: {len(reports)}")
        for r in reports:
            logger.info(f"[{r['severity']}] {r['rule_id']} (Target: {r['target_tag']}): {r['message']}")
            
        # Log generated files
        files = final_state.get("deliverables", {})
        logger.info("\nGenerated Deliverables:")
        for format_name, file_path in files.items():
            logger.info(f"- {format_name.upper()}: {file_path}")
            
        # Log loops run
        logger.info(f"\nFocused Re-Extraction Loops Run: {final_state.get('re_extraction_count', 0)}")
        logger.info(f"Total revision log events: {len(final_state.get('revision_history', []))}")
        
    except Exception as e:
        logger.exception(f"Pipeline execution encountered an error: {e}")

if __name__ == "__main__":
    main()
