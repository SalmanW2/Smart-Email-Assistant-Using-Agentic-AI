import logging
import httpx
from typing import List, Optional
from config import settings

logger = logging.getLogger(__name__)

async def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generates a 768-dimensional vector embedding for a given text
    using Google's text-embedding-004 model via direct REST API.
    This bypasses SDK version mismatches and v1alpha/v1beta routing errors.
    """
    if not text or not text.strip() or not settings.GEMINI_API_KEY:
        return None
        
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "model": "models/text-embedding-004",
            "content": {
                "parts": [{"text": text}]
            }
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            
            if resp.status_code == 200:
                data = resp.json()
                if "embedding" in data and "values" in data["embedding"]:
                    values = data["embedding"]["values"]
                    logger.debug(f"Successfully generated {len(values)}-dimensional vector embedding via REST.")
                    return values
            else:
                logger.error(f"REST Embedding API Error {resp.status_code}: {resp.text}")
                
        return None
    except Exception as e:
        logger.error(f"Error generating embedding via REST: {e}")
        return None
