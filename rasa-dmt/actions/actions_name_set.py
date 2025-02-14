from typing import Any, Dict
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

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