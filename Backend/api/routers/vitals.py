"""Web Vitals endpoint
Receives performance metrics (LCP, FCP, CLS, INP, TTFB) from the frontend.
"""

import logging
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vitals", tags=["Web Vitals"])


@router.post("")
async def receive_vitals(request: Request):
    try:
        body = await request.json()
        logger.info(f"Web Vitals: {body.get('name')} = {body.get('value')} (id={body.get('id')}, href={body.get('href')})")
    except Exception as e:
        logger.warning(f"Failed to parse vitals payload: {e}")
    return {"ok": True}
