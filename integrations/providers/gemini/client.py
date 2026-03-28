import json
import logging
from google import genai
from google.genai import types
from django.conf import settings
from ..base import BaseIntegrationProvider

logger = logging.getLogger(__name__)

class GeminiProvider(BaseIntegrationProvider):
    """Bridge: Pure logic for talking to Google GenAI API."""

    def is_configured(self):
        return bool(settings.GEMINI_API_KEY)

    def get_suggestions(self, context_str, prompt_template=None):
        """
        Generic suggestion engine.
        Args:
            context_str (str): Raw data context for Gemini.
            prompt_template (str): Optional override for the prompt.
        """
        if not self.is_configured():
            return []

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        prompt = prompt_template or f"""
        Context: {context_str}
        Suggest 3 short, actionable notifications based on this data.
        Return as a JSON list of strings.
        """

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.5),
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini Bridge error: {e}")
            return []
