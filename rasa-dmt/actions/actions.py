import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from typing import Any, Dict
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
# RAG image
from pymilvus import connections,Collection
from reranker import get_openai_response
# API
import requests
from datetime import datetime, timedelta
# Tokens
from dotenv import load_dotenv
import jwt
import base64
import hashlib
# Encryption
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

load_dotenv()

milvus_host = 'milvus-standalone-rasa'
milvus_port = '19530'
collection_name = 'rasa'

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
            
            connections.connect("default", host=milvus_host, port=milvus_port, user="root", password="Milvus")
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

class WhatsMyName(Action):
    def name(self) -> str:
        return "action_whats_my_name"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]):

        username = tracker.get_slot("user_account")
        role = tracker.get_slot("user_role")
        auth = tracker.get_slot("user_auth")
        user_id = tracker.sender_id

        if username:
            dispatcher.utter_message(text=f"Your name is {username}, id is {user_id}, role is {role}, auth is {auth}")
        else:
            dispatcher.utter_message(text="No name found")
        return []
    
class NameSet(Action):
    def name(self) -> str:
        return "action_name_set"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]):

        username = tracker.latest_message['entities'][0]['value']
        role = tracker.latest_message['entities'][1]['value']
        botInit = tracker.get_slot("user_botinit")

        print(username, role)

        if not botInit:
            return [SlotSet("user_account", username), SlotSet("user_role", role), SlotSet("user_botinit", True)]
        else:
            dispatcher.utter_message(text="Only admin can use this command")
            return []
        
class FetchWeather(Action):
    def name(self) -> str:
        return "action_fetch_weather"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> list:
        location = tracker.get_slot("location")

        if not location:
            dispatcher.utter_message(text="Location not provided.")
            return []

        location = location.title()
        api_url = f"https://api.data.gov.my/weather/forecast?contains={location}@location__location_name&limit=10"

        print(f"Fetching weather data from: {api_url}")

        try:
            response = requests.get(api_url)
            response.raise_for_status()
            weather_data = response.json()

            if weather_data:
                today = datetime.now().strftime("%Y-%m-%d")
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                
                for forecast in weather_data:
                    date = forecast['date']
                    if date in [today, tomorrow]:
                        location_name = forecast['location']['location_name']
                        summary_forecast = forecast['summary_forecast']
                        summary_when = forecast['summary_when']
                        min_temp = forecast['min_temp']
                        max_temp = forecast['max_temp']
                        
                        message = (f"The weather in {location_name} on {date} is {summary_forecast} during {summary_when} "
                                   f"with a minimum temperature of {min_temp}°C and a maximum temperature of {max_temp}°C.")
                        dispatcher.utter_message(text=message)
            else:
                dispatcher.utter_message(text=f"No weather data available for {location}.")
        except requests.RequestException as e:
            dispatcher.utter_message(text="Failed to fetch weather data.")
            print(f"Error fetching weather data: {e}")

        return []
    

class InitBot(Action):
    def name(self) -> str:
        return "action_init_bot"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]):
        try:
            token = tracker.latest_message['entities'][0]['value']
          
            user_info = verifyToken(token)

            print(f"User info: {user_info}")

            if user_info:
                return [SlotSet("user_account", user_info['user_account']), SlotSet("user_role", user_info['role']), SlotSet("user_auth", True)]
            else:
                dispatcher.utter_message(text="An unexpected error occurred. Please try again later.")
        except (IndexError, ValueError) as e:
            dispatcher.utter_message(text=f"Error: {str(e)}")
        except Exception as e:
            dispatcher.utter_message(text="An unexpected error occurred.")
            print(f"Unexpected error: {str(e)}")
        
        return []
        
        
        

def verifyToken(token):
        try:
            jwt_key = os.getenv("JWT_KEY")
            
            decoded_token = jwt.decode(token, jwt_key, algorithms=['HS256'])
            print("Token is valid.")
            
            encrypted_user_account = decoded_token.get('user_account')
            encrypted_role = decoded_token.get('role')
            
            user_account = decrypt_claim(encrypted_user_account)
            role = decrypt_claim(encrypted_role)


            print(f"User Account (user_account): {user_account}")
            print(f"Role (role): {role}")
            return {"user_account": user_account, "role": role}
            
        except jwt.ExpiredSignatureError:
            print("Token has expired.")
            raise ValueError("Token has expired.")
            
        except jwt.InvalidTokenError:
            print("Invalid token.")
            raise ValueError("Invalid token.")
        
def decrypt_claim(encrypted_claim):
    raw_key = os.getenv("ENCRYPTION_KEY") 
    encrypted_bytes = base64.b64decode(encrypted_claim)

    md5 = hashlib.md5()
    md5.update(raw_key.encode('utf-8'))
    key = md5.digest()

    encrypted_bytes = base64.b64decode(encrypted_claim)
    
    # AES decryption using ECB mode
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_bytes = decryptor.update(encrypted_bytes) + decryptor.finalize()
    
    # Decode decrypted bytes to UTF-8 and strip padding
    return decrypted_bytes.decode('utf-8').strip()