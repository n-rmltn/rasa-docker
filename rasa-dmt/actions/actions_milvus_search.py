import sys
import os
import json
import requests
from typing import Any, Dict
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from pymilvus import connections,Collection
from dotenv import load_dotenv

load_dotenv()

milvus_host = 'milvus-standalone-rasa'
milvus_port = '19530'
collection_name = 'rasa'
user_name='rasabot'
user_password='rasabot'

def get_openai_embeddings(api_key: str, input_text: str) -> list[float]:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "text-embedding-3-small",
                "input": input_text
            }
            response = requests.post("https://api.openai.com/v1/embeddings", headers=headers, json=data)
            response.raise_for_status()
            embeddings = response.json()["data"][0]["embedding"]
            return embeddings

class MilvusSearchAction(Action):
    def name(self) -> str:
        return "action_milvus_search"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]):
        try:
            api_key = os.getenv("OPENAI_API_KEY")

            user_input = tracker.latest_message.get('text')
            user_role = tracker.get_slot("user_role")

            query_vec = get_openai_embeddings(api_key, user_input)
            
            connections.connect("default", host=milvus_host, port=milvus_port, user=user_name, password=user_password)
            collection = Collection(name=collection_name)

            search_results = collection.search(
                data=[query_vec],
                anns_field="vector",
                output_fields=["text"],
                expr=f"ARRAY_CONTAINS(permission, '{user_role}')",
                limit=3,
                param={"metric_type": "L2", "params": {}},  
            )[0]

            language = tracker.get_slot('language')

            image_url, text = get_openai_response(search_results, user_input, language)

            dispatcher.utter_message(text=text, image=image_url)
            return []

        except Exception as e:
            # Handle the error
            dispatcher.utter_message(text="An error occurred while processing your request. Please try again later.")
            print(f"Error: {str(e)}")
            return []

def get_openai_response(search_results, user_input, language):
    api_key = os.getenv("OPENAI_API_KEY")

    # image_data = []
    formatted_results = []

    for result in search_results:
        text = result.entity.text
        formatted_results.append(f"{{}}\n{text}")
        # image_data.append({
        #     "type": "image_url",
        #     "image_url": {
        #         "url": image_path
        #     }
        # })

    output = "\n".join(f"{i}. {formatted_result}" for i, formatted_result in enumerate(formatted_results, start=1))

    prompt = "Given the following information, please provide an answer based solely on one relevant document that best addresses the user's query.\nReference only the most applicable document for the answer, and include any available images from the same document.\nIf the document contains no image, use the placeholder image provided.\n\n===\nRelevant Documents\n" + output + "\n\n===\nCurrent Conversation\nTranscript of the current conversation, use it to determine the context of the question:\nUSER:" + user_input + "\n\n===\nWhen answering, ensure that:\n- The answer is grounded in the provided documents and conversation context.\n- Always try to answer the query if applicable document or context is available, even if no image is provided.\nKeep responses concise (2 to 3 sentences) and within 200 - 300 words.\n- The information from the summarised document does not lose or change any of its meanings.\n- Do not refer to 'provided documents' in your response.\n- If an image is available from the chosen document, include its URL.\n- If no image is available in the referenced document, use the default placeholder URL:\nhttps://cdn.pixabay.com/photo/2015/11/03/08/56/question-mark-1019820_1280.jpg\nIf the answer is not known or cannot be determined from the provided documents or context, please state that you do not know to the user.\nYour response should be in a json format with 'image_url' for the appropriate image url and 'text' for your answer.\n Your response should be in simple " + language + "."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    """
        Add *image_data to content field in payload if required to send image to OpenAI
        However, reranking search query results does not require sending image data to OpenAI
    """
    
    payload = {
        "model": "gpt-4o-mini",
        "response_format": { "type":"json_object" },
        "messages": [
            {
            "role": "user",
            "content": [
                {
                "type": "text",
                "text": prompt,
                }
            ],
            }
        ],
    }
    
    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        content_str = response.json()['choices'][0]['message']['content']
        content_json = json.loads(content_str)
        image_url = content_json['image_url']
        text = content_json['text']
        print(prompt)
        print(content_str)
        return image_url, text
    
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None, None
    
    except (KeyError, ValueError) as e:
        print(f"An error occurred while parsing the response: {e}")
        return None, None
