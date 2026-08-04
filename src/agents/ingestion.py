"""
Ingestion Agent — Universal Engineering Drawing Ingestor.

Responsible for:
  1. Rasterizing PDF documents to images (PyMuPDF → pdf2image fallback)
  2. Detecting drawing type from title block and OCR text
  3. Extracting drawing metadata (number, revision, title, discipline)
  4. Uploading the primary page to Google GenAI File API for downstream VLM calls

Designed to be drawing-type agnostic — works equally well for P&ID,
Electrical Layouts, Earthing Layouts, SLDs, Structural, HVAC, etc.
"""
import os
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from src.agents.base import BaseAgent
from src.state import GraphState

logger = logging.getLogger(__name__)


class DrawingMetadata(BaseModel):
    """
    Pydantic schema for Engineering Drawing Metadata extracted by the Ingestion Agent.
    """
    drawing_type: str = Field(
        description="Drawing classification (e.g., PID, ELECTRICAL_LAYOUT, EARTHING_LAYOUT, SLD, HVAC_LAYOUT, STRUCTURAL_LAYOUT, GENERIC)"
    )
    discipline: str = Field(
        description="Engineering discipline (e.g., Process, Instrumentation, Electrical, Mechanical, Civil)"
    )
    drawing_number: str = Field(
        description="Document reference number from the title block (e.g., 26-000001-001)"
    )
    title: str = Field(
        description="Title of the drawing as written on the drawing (e.g., LIGHTING LAYOUT - 1, EARTHING LAYOUT)"
    )
    revision: str = Field(
        description="Document revision number or code (e.g., Rev 01, Rev A, 0)"
    )
    client_name: Optional[str] = Field(
        default=None,
        description="Name of the client or owner if shown in the title block"
    )
    page_count: int = Field(
        description="Total number of pages/sheets in the package"
    )


class IngestionAgent(BaseAgent):
    """
    Agent responsible for analyzing incoming files, detecting drawing type,
    extracting metadata, and preprocessing/rasterizing documents.
    """

    def run(self, state: GraphState) -> Dict[str, Any]:
        logger.info("Running Ingestion Agent...")
        documents = state.get("raw_documents", [])
        if not documents:
            raise ValueError("No input documents provided to Ingestion Agent.")

        first_doc = documents[0]
        rasterized_pages = []

        file_ext = os.path.splitext(first_doc)[1].lower()
        filename = os.path.basename(first_doc)

        if file_ext == ".pdf":
            rasterized_pages = self._rasterize_pdf(first_doc)
            if not rasterized_pages:
                rasterized_pages = [first_doc]
        else:
            rasterized_pages = [first_doc]

        use_mocks = state.get("use_mocks", True)
        if use_mocks:
            logger.info("Demo Mock Fallbacks are ENABLED. Using default mock metadata.")
            metadata_dict = {
                "drawing_type": "PID",
                "discipline": "Process",
                "drawing_number": "26-000001-001",
                "title": "ENGINEERING DRAWING (MOCK)",
                "revision": "Rev 01",
                "client_name": "Unknown",
                "page_count": 1,
                "rasterized_pages": rasterized_pages,
            }
            return {
                "metadata": metadata_dict,
                "revision_history": state.get("revision_history", []) + [
                    {"action": "Ingestion completed (mock)", "pages_count": len(rasterized_pages)}
                ],
            }

        local_mode = state.get("local_mode", False)
        if local_mode:
            logger.info("Local Mode ENABLED. Extracting metadata via PaddleOCR + heuristics (no LLM).")
            try:
                from src.utils.preprocess import preprocess_for_ocr
                from src.utils.paddle_ocr import run_paddle_ocr, run_pdf_text_extraction
                from src.utils.tag_classifier import extract_metadata_from_paddle

                # Try PDF text layer first
                if first_doc.lower().endswith('.pdf'):
                    try:
                        pdf_items = run_pdf_text_extraction(first_doc)
                        if len(pdf_items) > 10:
                            metadata_dict = extract_metadata_from_paddle(pdf_items, filename=filename)
                            metadata_dict["rasterized_pages"] = rasterized_pages
                            logger.info(
                                f"Local mode metadata: type={metadata_dict.get('drawing_type')}, "
                                f"title='{metadata_dict.get('title')}'"
                            )
                            return {
                                "metadata": metadata_dict,
                                "revision_history": state.get("revision_history", []) + [
                                    {"action": f"Ingestion completed (local/PDF text layer) — {metadata_dict.get('drawing_type')}", "pages_count": len(rasterized_pages)}
                                ],
                            }
                    except Exception as pdf_err:
                        logger.warning(f"PDF text layer extraction failed ({pdf_err}). Falling back to OCR.")

                # OCR fallback
                proc_img = preprocess_for_ocr(rasterized_pages[0])
                paddle_items = run_paddle_ocr(proc_img)
                metadata_dict = extract_metadata_from_paddle(paddle_items, filename=filename)

            except Exception as e:
                logger.warning(f"Local metadata extraction failed ({e}). Using generic fallback.")
                from src.utils.drawing_type_detector import detect_drawing_type, DRAWING_TYPE_LABELS
                detected = detect_drawing_type(filename=filename)
                metadata_dict = {
                    "drawing_type": detected.value,
                    "discipline": DRAWING_TYPE_LABELS[detected]["discipline"],
                    "drawing_number": "UNKNOWN",
                    "title": "ENGINEERING DRAWING",
                    "revision": "0",
                    "client_name": "Unknown",
                    "page_count": 1,
                }

            metadata_dict["rasterized_pages"] = rasterized_pages
            return {
                "metadata": metadata_dict,
                "revision_history": state.get("revision_history", []) + [
                    {"action": f"Ingestion completed (local mode) — detected: {metadata_dict.get('drawing_type', 'UNKNOWN')}", "pages_count": len(rasterized_pages)}
                ],
            }

        # ── Gemini Vision mode ─────────────────────────────────────────────────
        uploaded_info = self.upload_file_to_api(rasterized_pages[0])

        if uploaded_info:
            meta_result = self._extract_metadata_via_vision(
                image_uri=uploaded_info["uri"],
                image_mime=uploaded_info["mime"],
                filename=filename,
            )
        else:
            meta_result = self._extract_metadata_via_vision(
                image_path=rasterized_pages[0],
                filename=filename,
            )

        metadata_dict = meta_result.model_dump()
        metadata_dict["rasterized_pages"] = rasterized_pages
        if uploaded_info:
            metadata_dict["primary_page_uri"] = uploaded_info["uri"]
            metadata_dict["primary_page_mime"] = uploaded_info["mime"]
            metadata_dict["primary_page_name"] = uploaded_info["name"]

        return {
            "metadata": metadata_dict,
            "revision_history": state.get("revision_history", []) + [
                {"action": f"Ingestion completed — detected: {metadata_dict.get('drawing_type', 'UNKNOWN')}", "pages_count": len(rasterized_pages)}
            ],
        }

    def _rasterize_pdf(self, pdf_path: str) -> list:
        """
        Convert PDF pages to PNG images using PyMuPDF (no poppler needed).
        Falls back to pdf2image if pymupdf is unavailable.
        Returns list of paths to rasterized PNG files.
        """
        output_dir = os.path.join(os.path.dirname(pdf_path), "rasterized")
        os.makedirs(output_dir, exist_ok=True)
        rasterized = []

        try:
            import pymupdf as fitz
            logger.info(f"Rasterizing PDF with PyMuPDF: '{pdf_path}'")
            doc = fitz.open(pdf_path)
            dpi = 300
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                page_path = os.path.join(output_dir, f"page_{page_num+1}.png")
                pix.save(page_path)
                rasterized.append(page_path)
                logger.info(f"  Rasterized page {page_num+1} → {page_path} ({pix.width}×{pix.height}px)")
            doc.close()
            logger.info(f"PyMuPDF rasterized {len(rasterized)} pages.")
            return rasterized
        except Exception as e:
            logger.warning(f"PyMuPDF rasterization failed ({e}). Trying pdf2image...")

        try:
            from pdf2image import convert_from_path
            logger.info(f"Rasterizing PDF with pdf2image: '{pdf_path}'")
            pages = convert_from_path(pdf_path, dpi=300)
            for idx, page in enumerate(pages):
                page_path = os.path.join(output_dir, f"page_{idx+1}.png")
                page.save(page_path, "PNG")
                rasterized.append(page_path)
            logger.info(f"pdf2image rasterized {len(rasterized)} pages.")
            return rasterized
        except Exception as e:
            logger.error(f"pdf2image rasterization also failed ({e}).")
            return []

    def _extract_metadata_via_vision(
        self,
        image_path: Optional[str] = None,
        image_uri: Optional[str] = None,
        image_mime: str = "image/png",
        filename: Optional[str] = None,
    ) -> DrawingMetadata:
        """
        Uses Gemini Vision API to inspect the drawing title block and extract metadata.
        Drawing-type detection is built into the schema and prompt — works for any discipline.
        """
        system_instruction = (
            "You are a professional engineering document ingestion system. "
            "Examine the provided engineering drawing image, look closely at the title block, "
            "sheet headers, and drawing notes. Extract structured metadata accurately. "
            "Identify the drawing type from the drawing content and title — it may be a P&ID, "
            "Electrical Layout, Earthing Layout, SLD, HVAC, Structural, or other discipline."
        )

        prompt = (
            "Extract the following metadata from this engineering drawing. "
            "Look carefully at the title block (usually bottom-right) and all sheet headers:\n\n"
            "- drawing_type: One of: PID, PFD, ELECTRICAL_LAYOUT, EARTHING_LAYOUT, SLD, "
            "HVAC_LAYOUT, STRUCTURAL_LAYOUT, ISOMETRIC, CABLE_SCHEDULE, GENERIC\n"
            "- discipline: Engineering discipline (Process, Electrical, Mechanical, Civil, etc.)\n"
            "- drawing_number: Unique document/sheet number from title block\n"
            "- title: Full title as written on the drawing (e.g., LIGHTING LAYOUT - 1, EARTHING LAYOUT)\n"
            "- revision: Revision character or number (e.g., 0, 1, A, B)\n"
            "- client_name: Owner or client name if shown\n"
            "- page_count: Total sheets if multi-sheet package, otherwise 1\n\n"
            f"Filename hint (may help identify drawing type): {filename or 'N/A'}"
        )

        try:
            return self.invoke_structured(
                schema=DrawingMetadata,
                prompt=prompt,
                system_instruction=system_instruction,
                image_path=image_path,
                image_mime=image_mime,
                image_uri=image_uri,
            )
        except Exception as e:
            logger.error(f"Gemini metadata extraction failed: {e}. Falling back to generic defaults.")
            # Use filename-based detection as last resort
            from src.utils.drawing_type_detector import detect_drawing_type, DRAWING_TYPE_LABELS
            detected = detect_drawing_type(filename=filename)
            label = DRAWING_TYPE_LABELS[detected]
            return DrawingMetadata(
                drawing_type=detected.value,
                discipline=label["discipline"],
                drawing_number="UNKNOWN",
                title=label["label"],
                revision="0",
                client_name="Unknown",
                page_count=1,
            )
