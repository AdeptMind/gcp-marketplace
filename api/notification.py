import requests
from config import settings

def send_slack_error(message: str):
    print(message)
    url = settings.slack_alert_url
    data_to_send = {
        "icon_emoji": ":alert:",
        "text": f"ERROR: {message}"
    }
    _ = requests.post(url, json=data_to_send)
