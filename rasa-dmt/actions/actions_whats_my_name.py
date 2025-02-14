from typing import Any, Dict
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

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