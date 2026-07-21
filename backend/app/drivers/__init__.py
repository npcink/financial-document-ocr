from app.core import config

if config.AI_MODE == "cloud":
    from app.drivers.ocr_cloud import ocr_image, ocr_pdf, get_ocr_client
    from app.drivers.llm_cloud import classify_and_extract, extract_fields_only, extract_missing_fields, check_llm_available
    MODEL_NAME = config.LLM_MODEL_CLOUD
else:
    from app.drivers.ocr_local import ocr_image, ocr_pdf, get_ocr_client
    from app.drivers.llm_local import classify_and_extract, extract_fields_only, extract_missing_fields, check_llm_available
    MODEL_NAME = config.LLM_MODEL_LOCAL
