import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from pymilvus import Collection, connections
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

load_dotenv()

@dataclass
class MilvusConfig:
    """Configuration for Milvus connection."""
    host: str = 'milvus-standalone-rasa'
    port: str = '19530'
    collection_name: str = 'rasa'
    username: str = 'rasabot'
    password: str = 'rasabot'

@dataclass
class OpenAIConfig:
    """Configuration for OpenAI API."""
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    default_image: str = "https://cdn.pixabay.com/photo/2015/11/03/08/56/question-mark-1019820_1280.jpg"

class OpenAIClient:
    """Client for interacting with OpenAI API."""
    
    def __init__(self, config: OpenAIConfig):
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate API configuration."""
        if not self.config.api_key:
            raise ValueError("OpenAI API key not found in environment variables")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

    def get_embeddings(self, input_text: str) -> List[float]:
        """Get embeddings for input text."""
        try:
            response = requests.post(
                f"{self.config.api_base}/embeddings",
                headers=self._get_headers(),
                json={
                    "model": self.config.embedding_model,
                    "input": input_text
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to get embeddings: {e}")

    def get_chat_response(self, prompt: str, language: str) -> Tuple[Optional[str], Optional[str]]:
        """Get chat completion response."""
        payload = {
            "model": self.config.chat_model,
            "response_format": {"type": "json_object"},
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": prompt
                }]
            }]
        }

        try:
            response = requests.post(
                f"{self.config.api_base}/chat/completions",
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            content = json.loads(response.json()['choices'][0]['message']['content'])
            return content.get('image_url'), content.get('text')
            
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            print(f"Error in chat completion: {e}")
            return None, None

class MilvusSearchAction(Action):
    """Rasa action for searching Milvus vector database."""

    def __init__(self):
        self.milvus_config = MilvusConfig()
        self.openai_config = OpenAIConfig()
        self.openai_client = OpenAIClient(self.openai_config)

    def name(self) -> str:
        """Return action name."""
        return "action_milvus_search"

    def _format_search_results(self, results: List[Any], user_input: str, language: str) -> str:
        """Format search results for prompt."""
        formatted_results = [
            f"{{}}\n{result.entity.text}"
            for result in results
        ]
        
        output = "\n".join(
            f"{i}. {result}"
            for i, result in enumerate(formatted_results, start=1)
        )

        return (
            f"Given the following information, please provide an answer based solely on one relevant "
            f"document that best addresses the user's query.\n"
            f"Reference only the most applicable document for the answer, and include any available "
            f"images from the same document.\n"
            f"If the document contains no image, use the placeholder image provided.\n\n"
            f"===\nRelevant Documents\n{output}\n\n"
            f"===\nCurrent Conversation\n"
            f"Transcript of the current conversation, use it to determine the context of the question:\n"
            f"USER:{user_input}\n\n"
            f"===\n"
            f"When answering, ensure that:\n"
            f"- The answer is grounded in the provided documents and conversation context.\n"
            f"- Always try to answer the query if applicable document or context is available, "
            f"even if no image is provided.\n"
            f"Keep responses concise (2 to 3 sentences) and within 200 - 300 words.\n"
            f"- The information from the summarised document does not lose or change any of its meanings.\n"
            f"- Do not refer to 'provided documents' in your response.\n"
            f"- If an image is available from the chosen document, include its URL.\n"
            f"- If no image is available in the referenced document, use the default placeholder URL:\n"
            f"{self.openai_config.default_image}\n"
            f"If the answer is not known or cannot be determined from the provided documents or context, "
            f"please state that you do not know to the user.\n"
            f"Your response should be in a json format with 'image_url' for the appropriate image url "
            f"and 'text' for your answer.\n"
            f"Your response should be in simple {language}."
        )

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute the Milvus search action."""
        try:
            user_input = tracker.latest_message.get('text')
            user_role = tracker.get_slot("user_role")
            language = tracker.get_slot('language')

            if not all([user_input, user_role, language]):
                raise ValueError("Missing required slots: user_input, user_role, or language")

            # Get embeddings for user input
            query_vec = self.openai_client.get_embeddings(user_input)

            # Connect to Milvus and search
            connections.connect(
                "default",
                host=self.milvus_config.host,
                port=self.milvus_config.port,
                user=self.milvus_config.username,
                password=self.milvus_config.password
            )

            collection = Collection(name=self.milvus_config.collection_name)
            search_results = collection.search(
                data=[query_vec],
                anns_field="vector",
                output_fields=["text"],
                expr=f"ARRAY_CONTAINS(permission, '{user_role}')",
                limit=3,
                param={"metric_type": "L2", "params": {}}
            )[0]

            # Format prompt and get OpenAI response
            prompt = self._format_search_results(search_results, user_input, language)
            image_url, text = self.openai_client.get_chat_response(prompt, language)

            if text:
                dispatcher.utter_message(text=text, image=image_url or self.openai_config.default_image)
            else:
                dispatcher.utter_message(text="I apologize, but I couldn't process your request at this time.")

        except Exception as e:
            print(f"Error in MilvusSearchAction: {str(e)}")
            dispatcher.utter_message(
                text="I encountered an error while processing your request. Please try again later."
            )

        finally:
            connections.disconnect("default")

        return []
