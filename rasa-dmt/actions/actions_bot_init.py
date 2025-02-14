import os
import jwt
import base64
import hashlib
from typing import Any, Dict
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

load_dotenv()

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
    decrypted_text = decrypted_bytes.decode('utf-8')
    return decrypted_text.rstrip('\x06')