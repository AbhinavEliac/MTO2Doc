import os
import logging

logger = logging.getLogger(__name__)

_got_model = None
_got_tokenizer = None

def get_got_ocr_model():
    """
    Dynamic loader for GOT-OCR 2.0. Checks for torch/transformers dependencies
    and initializes the model on GPU (if CUDA is available) or CPU.
    """
    global _got_model, _got_tokenizer
    if _got_model is None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
            logger.info("Initializing GOT-OCR 2.0 (ucaslcl/GOT-OCR2_0)...")
            
            model_id = "ucaslcl/GOT-OCR2_0"
            _got_tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading GOT-OCR 2.0 onto device: {device}...")
            
            _got_model = AutoModel.from_pretrained(
                model_id, 
                trust_remote_code=True, 
                low_cpu_mem_usage=True, 
                device_map=device, 
                use_safetensors=True, 
                pad_token_id=_got_tokenizer.eos_token_id
            )
            _got_model = _got_model.eval()
            if device == "cuda":
                _got_model = _got_model.cuda()
                
            logger.info("GOT-OCR 2.0 model loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize local GOT-OCR 2.0: {e}")
            raise e
            
    return _got_model, _got_tokenizer

def perform_got_ocr(image_path: str, ocr_type: str = "ocr") -> str:
    """
    Run inference on an image path using GOT-OCR 2.0.
    ocr_type can be 'ocr' (plain text) or 'format' (markdown/latex).
    """
    model, tokenizer = get_got_ocr_model()
    logger.info(f"Executing GOT-OCR 2.0 chat inference for: {image_path}")
    res = model.chat(tokenizer, image_path, ocr_type=ocr_type)
    return res
