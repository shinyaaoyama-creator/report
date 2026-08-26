import logging
import time

logger = logging.getLogger(__name__)

MODEL = "gemini-flash-latest"


def call_with_retries(client, model: str, prompt: str, max_retries: int = 3) -> str | None:
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text
        except Exception:
            logger.warning("gemini call failed (attempt %d/%d)", attempt + 1, max_retries, exc_info=True)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return None
