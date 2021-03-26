# - *- coding: utf- 8 - *-
import requests
from urllib.parse import quote
from requests.auth import HTTPBasicAuth

class WebAppAPI():
    WEB_APP_URL = "http://admin.iot-mas-server.hr"
    EMAIL_URL = f"{WEB_APP_URL}/api/v1/email"
    LOG_URL = f"{WEB_APP_URL}/api/v1/log"

    AUTH = HTTPBasicAuth("admin", "nimda")
    agentName = None

    def __init__(self, agentName) -> None:
        super().__init__()
        self.agentName = agentName

    def log(self, message):
        requests.post(self.LOG_URL, data={"agentName": self.agentName, "message": message}, auth=self.AUTH)

    def sendEmail(self, to, body):
        requests.post(self.EMAIL_URL, data={"to": to, "body": body}, auth=self.AUTH)


class WebAppServicesAPI():
    WEB_APP_URL = "http://iot-mas-services.hr"
    SERVICES_CENTRES_FOR_DEVICE_URL = f"{WEB_APP_URL}/api/v1/service-centres/service?device="

    AUTH = HTTPBasicAuth('', '')

    def __init__(self) -> None:
        super().__init__()

    def getAllServicesForDevice(self, deviceName):
        data = []
        url = f"{self.SERVICES_CENTRES_FOR_DEVICE_URL}{quote(deviceName)}"
        response = requests.get(url, auth=self.AUTH)
        if response.status_code == 200:
            data = response.json()
        else:
            print(f"ERROR: Ne mogu dohvatiti podatke! {response.text}")
        return data
