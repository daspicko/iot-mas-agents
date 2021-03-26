# - *- coding: utf- 8 - *-
import requests

class MockedSensor:
    MOCKED_SENSOR_API = "http://sensors.iot-mas-server.hr/sensorvalue.php?name="

    def __init__(self, name) -> None:
        super().__init__()
        self.name = name
        self.url = f"{self.MOCKED_SENSOR_API}{name}"

    def getValue(self):
        r = requests.get(url=self.url)
        try:
            return r.json()["value"]
        except:
            return -1