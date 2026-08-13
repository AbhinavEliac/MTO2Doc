import os
import logging
from PIL import Image
from src.graph import create_workflow
from src.state import GraphState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("verify_pipeline")

def create_mock_drawing(path: str):
    """
    Creates a tiny mock image drawing using PIL to serve as ingestion input.
    """
    img = Image.new("RGB", (800, 600), color="white")
    img.save(path)
    logger.info(f"Created dummy drawing file: '{path}'")

def run_verification():
    mock_input = "mock_drawing.png"
    create_mock_drawing(mock_input)
    
    logger.info("Initializing workflow...")
    workflow = create_workflow()
    app = workflow.compile()
    
    initial_state: GraphState = {
        "raw_documents": [mock_input],
        "metadata": {},
        "engineering_context": {},
        "extracted_entities": {
            "text_elements": [],
            "symbols": [],
            "relations": [],
            "geometry": {}
        },
        "engineering_graph": None,
        "validation_reports": [],
        "missing_entities": [],
        "revision_history": [],
        "deliverables": {},
        "re_extraction_count": 0,
        "max_re_extractions": 3,
        "ocr_engine": "gemini",
        "use_mocks": True,
        "local_mode": False,
        "re_extracted_targets": []

    }
    
    logger.info("Invoking LangGraph pipeline...")
    final_state = app.invoke(initial_state)
    
    logger.info("Verifying outcomes...")
    
    # 1. Verify page metadata
    metadata = final_state.get("metadata", {})
    print("METADATA FOUND:", metadata)
    assert metadata.get("title") or metadata.get("drawing_type"), "Metadata missing"
    logger.info("✓ Metadata verification passed.")
    
    # 2. Verify graph compiled
    graph = final_state.get("engineering_graph")
    assert graph is not None, "EngineeringGraph was not compiled"
    assert len(graph.equipment) >= 6, f"Expected at least 6 equipment items, got {len(graph.equipment)}"
    assert len(graph.lines) >= 6, f"Expected at least 6 line items, got {len(graph.lines)}"
    assert len(graph.instruments) >= 15, f"Expected at least 15 instrument items, got {len(graph.instruments)}"
    logger.info("✓ Graph size compilation checks passed.")
    
    # 3. Verify valve size derivation (the key requirement)
    # Check valve 26CB9131 is merged in the re-extraction node. It should have size derived from line 2"-PL-26-9115-FC11S-00.
    valves = graph.valves
    # Since we added 26CB9131 on the re-extraction run, we should see it
    re_extracted_valve = next((v for v in valves if v.tag == "26CB9131"), None)
    assert re_extracted_valve is not None, "Check valve 26CB9131 was not successfully re-extracted and merged"
    assert re_extracted_valve.size == "2\"", f"Expected valve 26CB9131 size to be derived as 2\", but got {re_extracted_valve.size}"
    logger.info("✓ Valve size derivation (derived from parent line size) passed successfully.")
    
    # 4. Verify loops run
    re_runs = final_state.get("re_extraction_count", 0)
    assert re_runs == 1, f"Expected exactly 1 focused re-extraction loop, but got {re_runs}"
    logger.info("✓ Re-extraction conditional loops executed exactly once.")
    
    # 5. Verify deliverable files exist
    deliverables = final_state.get("deliverables", {})
    expected_formats = ["excel", "json_graph", "aveva_xml", "comos_json", "sppid_csv"]
    for fmt in expected_formats:
        assert fmt in deliverables, f"Missing deliverable key: {fmt}"
        file_path = deliverables[fmt]
        assert os.path.exists(file_path), f"File not found on disk for format {fmt}: {file_path}"
        logger.info(f"✓ Verified deliverable file generated: {os.path.basename(file_path)}")
        
    logger.info("\n" + "="*50 + "\nAll Verification Pipeline Checks Passed Successfully!\n" + "="*50)
    
    # Clean up mock file
    if os.path.exists(mock_input):
        os.remove(mock_input)
    # Clean up cropped regions dir
    crops_dir = os.path.join(os.getcwd(), "crops")
    if os.path.exists(crops_dir):
        for f in os.listdir(crops_dir):
            os.remove(os.path.join(crops_dir, f))
        os.rmdir(crops_dir)

if __name__ == "__main__":
    run_verification()
