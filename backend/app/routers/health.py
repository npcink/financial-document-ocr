import asyncio
import inspect
from fastapi import APIRouter
from app.models.schemas import HealthResponse
from app.services.llm import check_llm_available, MODEL_NAME

router = APIRouter()


@router.get("/", response_model=HealthResponse)
async def health_check():
    ocr_available = False
    try:
        from app.services.ocr import get_ocr_client
        client = get_ocr_client()
        if inspect.iscoroutinefunction(client.list):
            await client.list()
        else:
            await asyncio.to_thread(client.list)
        ocr_available = True
    except Exception:
        ocr_available = False

    llm_available = await check_llm_available()

    status = "healthy" if ocr_available and llm_available else "degraded"
    if not ocr_available and not llm_available:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        ocr_available=ocr_available,
        llm_available=llm_available,
        llm_model=MODEL_NAME,
    )
