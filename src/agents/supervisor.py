import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from src.agents.base import BaseAgent
from src.state import GraphState

logger = logging.getLogger(__name__)

class GridCoordinate(BaseModel):
    label: str = Field(description="Grid cell designator (e.g., D5, B9)")
    ymin: float = Field(description="Normalized ymin coordinate [0.0 - 1.0]")
    xmin: float = Field(description="Normalized xmin coordinate [0.0 - 1.0]")
    ymax: float = Field(description="Normalized ymax coordinate [0.0 - 1.0]")
    xmax: float = Field(description="Normalized xmax coordinate [0.0 - 1.0]")

class LayoutSegmentation(BaseModel):
    """
    Pydantic schema representing visual sub-divisions of the P&ID layout.
    """
    major_regions: List[GridCoordinate] = Field(description="Key grid sectors containing primary equipment and piping junctions")
    legend_region: GridCoordinate = Field(description="Grid coordinates encompassing the legend, symbols or notes block")
    title_block_region: GridCoordinate = Field(description="Grid coordinates encompassing the drawing details title block")

class SupervisorAgent(BaseAgent):
    """
    Agent that acts as the Gemini Vision Supervisor, orchestrating parallel
    extraction by segmenting the drawing image into grid quadrants.
    """
    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Gemini Vision Supervisor...")
        
        metadata = state.get("metadata", {})
        rasterized_pages = metadata.get("rasterized_pages", [])
        
        if not rasterized_pages:
            # Graceful fallback: Use document path
            rasterized_pages = state.get("raw_documents", [])
            
        primary_page = rasterized_pages[0]
        
        use_mocks = state.get("use_mocks", True)
        if use_mocks:
            logger.info("Demo Mock Fallbacks are ENABLED. Skipping visual layout segmentation.")
            segmentation = LayoutSegmentation(
                major_regions=[
                    GridCoordinate(label="B5", ymin=0.1, xmin=0.3, ymax=0.5, xmax=0.6),
                    GridCoordinate(label="C9", ymin=0.2, xmin=0.6, ymax=0.6, xmax=0.9),
                    GridCoordinate(label="F3", ymin=0.5, xmin=0.1, ymax=0.8, xmax=0.4)
                ],
                legend_region=GridCoordinate(label="Notes", ymin=0.7, xmin=0.0, ymax=1.0, xmax=0.3),
                title_block_region=GridCoordinate(label="TitleBlock", ymin=0.8, xmin=0.7, ymax=1.0, xmax=1.0)
            )
        elif state.get("local_mode", False):
            logger.info("Local Mode ENABLED. Using default grid layout coordinates (no LLM).")
            segmentation = LayoutSegmentation(
                major_regions=[
                    GridCoordinate(label="A-C_left",   ymin=0.0,  xmin=0.0,  ymax=0.35, xmax=0.5),
                    GridCoordinate(label="A-C_right",  ymin=0.0,  xmin=0.5,  ymax=0.35, xmax=1.0),
                    GridCoordinate(label="D-H_full",   ymin=0.35, xmin=0.0,  ymax=0.75, xmax=1.0),
                ],
                legend_region=GridCoordinate(label="Notes", ymin=0.75, xmin=0.0, ymax=1.0, xmax=0.35),
                title_block_region=GridCoordinate(label="TitleBlock", ymin=0.82, xmin=0.65, ymax=1.0, xmax=1.0)
            )
        else:
            segmentation = self._segment_layout_via_vision(primary_page)
        
        # Prepare sub-tasks for parallel vision agents
        # We can store the visual zones in state so parallel nodes know what crops to check
        grid_regions = [region.model_dump() for region in segmentation.major_regions]
        
        # Merge grid division layout mapping to downstream agents
        metadata["grid_segmentation"] = segmentation.model_dump()
        
        return {
            "metadata": metadata,
            "revision_history": state.get("revision_history", []) + [{"action": "Segmented drawing grid layout"}]
        }

    def _segment_layout_via_vision(self, image_path: str) -> LayoutSegmentation:
        """
        Invokes Gemini Vision to identify layout margins and divide the drawing.
        """
        system_instruction = (
            "You are an expert design engineer. Analyze the border grids of the P&ID drawing sheet "
            "and segment the drawing layout into structured region cells."
        )
        
        prompt = (
            "Look at the drawing boundaries. There are alphabetical labels (A to J) on the left/right "
            "and numbers (1 to 12) on the top/bottom. Identify the normalized bounding boxes [ymin, xmin, ymax, xmax] "
            "for the following:\n"
            "- Three major grid cells containing high-density equipment/lines (e.g. where compressors or scrubbers sit)\n"
            "- The legend and notes block region\n"
            "- The bottom-right title block region\n"
            "Return normalized coordinates in the range [0.0 - 1.0]."
        )
        
        try:
            return self.invoke_structured(
                schema=LayoutSegmentation,
                prompt=prompt,
                system_instruction=system_instruction,
                image_path=image_path
            )
        except Exception as e:
            logger.error(f"Supervisor layout segmentation failed: {e}. Using fallback coordinates.")
            # Default fallbacks representing typical P&ID grid sectors (A1-J12)
            return LayoutSegmentation(
                major_regions=[
                    GridCoordinate(label="B5", ymin=0.1, xmin=0.3, ymax=0.5, xmax=0.6),
                    GridCoordinate(label="C9", ymin=0.2, xmin=0.6, ymax=0.6, xmax=0.9),
                    GridCoordinate(label="F3", ymin=0.5, xmin=0.1, ymax=0.8, xmax=0.4)
                ],
                legend_region=GridCoordinate(label="Notes", ymin=0.7, xmin=0.0, ymax=1.0, xmax=0.3),
                title_block_region=GridCoordinate(label="TitleBlock", ymin=0.8, xmin=0.7, ymax=1.0, xmax=1.0)
            )
        
