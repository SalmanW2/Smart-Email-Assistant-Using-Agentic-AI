import logging
import asyncio
from typing import List, Optional
from google import genai
from config import settings

logger = logging.getLogger(__name__)

# Initialize a separate genai client for embeddings 
try:
    _gemini_client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options={'api_version': 'v1alpha'}
    )
except Exception as e:
    logger.error(f"Failed to initialize Gemini Client for embeddings: {e}")
    _gemini_client = None

async def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generates a 768-dimensional vector embedding for a given text
    using Google's text-embedding-004 model.
    """
    if not _gemini_client or not text or not text.strip():
        return None
        
    try:
        # Run the synchronous embed_content in an asyncio thread to avoid blocking the event loop
        response = await asyncio.to_thread(
            _gemini_client.models.embed_content,
            model='text-embedding-004',
            contents=text
        )
        
        # In the new google-genai SDK, response is typically an EmbedContentResponse
        # containing a list of Embeddings.
        if response and getattr(response, "embeddings", None):
            logger.debug(f"Successfully generated {len(response.embeddings[0].values)}-dimensional vector embedding.")
            return response.embeddings[0].values
        return None
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return None
