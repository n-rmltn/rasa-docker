import requests
from typing import Any, Dict
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from datetime import datetime, timedelta

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