from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

class WeatherForecast:
    """Data class to store weather forecast information."""
    def __init__(self, date: str, location_name: str, summary_forecast: str,
                 summary_when: str, min_temp: float, max_temp: float):
        self.date = date
        self.location_name = location_name
        self.summary_forecast = summary_forecast
        self.summary_when = summary_when
        self.min_temp = min_temp
        self.max_temp = max_temp

    def format_message(self) -> str:
        """Format weather information into a readable message."""
        return (
            f"The weather in {self.location_name} on {self.date} is {self.summary_forecast} "
            f"during {self.summary_when} with a minimum temperature of {self.min_temp}°C "
            f"and a maximum temperature of {self.max_temp}°C."
        )

class FetchWeather(Action):
    """Action to fetch weather information from the Malaysian weather API."""

    API_BASE_URL = "https://api.data.gov.my/weather/forecast"

    def name(self) -> str:
        """Return the action name as required by Rasa."""
        return "action_fetch_weather"

    def _get_api_url(self, location: str) -> str:
        """Construct the API URL for the weather request."""
        return f"{self.API_BASE_URL}?contains={location}@location__location_name&limit=10"

    def _get_target_dates(self) -> List[str]:
        """Get today's and tomorrow's dates in the required format."""
        today = datetime.now()
        return [
            today.strftime("%Y-%m-%d"),
            (today + timedelta(days=1)).strftime("%Y-%m-%d")
        ]

    def _parse_forecast(self, forecast_data: Dict[str, Any]) -> Optional[WeatherForecast]:
        """Parse raw forecast data into a WeatherForecast object."""
        try:
            return WeatherForecast(
                date=forecast_data['date'],
                location_name=forecast_data['location']['location_name'],
                summary_forecast=forecast_data['summary_forecast'],
                summary_when=forecast_data['summary_when'],
                min_temp=forecast_data['min_temp'],
                max_temp=forecast_data['max_temp']
            )
        except KeyError as e:
            print(f"Missing required field in forecast data: {e}")
            return None

    def _fetch_weather_data(self, location: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch weather data from the API."""
        api_url = self._get_api_url(location)
        print(f"Fetching weather data from: {api_url}")

        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching weather data: {e}")
            return None

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute the weather fetch action."""
        location = tracker.get_slot("location")
        if not location:
            dispatcher.utter_message(text="I need a location to check the weather. Please provide a location.")
            return []

        location = location.title()
        weather_data = self._fetch_weather_data(location)

        if not weather_data:
            dispatcher.utter_message(text="Sorry, I couldn't fetch the weather data at the moment.")
            return []

        target_dates = self._get_target_dates()
        forecasts_sent = False

        for forecast_data in weather_data:
            if forecast_data['date'] in target_dates:
                forecast = self._parse_forecast(forecast_data)
                if forecast:
                    dispatcher.utter_message(text=forecast.format_message())
                    forecasts_sent = True

        if not forecasts_sent:
            dispatcher.utter_message(text=f"No weather forecast available for {location}.")

        return []