# - *- coding: utf- 8 - *-
import base64
import json

class XmppData:
    def __init__(self, hostname, jid, password) -> None:
        super().__init__()
        self.hostname = hostname
        self.jid = f"{jid}@{hostname}"
        self.password = password


class AgentData:
    def __init__(self, data, test=False) -> None:
        super().__init__()
        if test:
            self.mockData()
        else:
            self.readDataFromParameters(data)

    def readDataFromParameters(self, receivedData):
        receivedData_bytes = receivedData.encode('utf-8')
        message_bytes = base64.b64decode(receivedData_bytes)
        message = message_bytes.decode('utf-8')
        data = json.loads(message)

        self.name = data["name"]
        self.xmpp = XmppData(data["xmpp"]["hostname"], data["xmpp"]["jid"], data["xmpp"]["password"])
        try:
            self.wgiPort = data["wgiPort"]
        except KeyError:
            self.wgiPort = 10000
        try:
            self.data = data["data"]
        except KeyError:
            self.data = {}

    def mockData(self):
        self.name = "Testni agent"
        self.xmpp = XmppData("openfire.iot-mas-server.hr", "test", "0000")
        self.wgiPort = 10000
        self.data = {}

    def __str__(self) -> str:
        return f"Name: {self.name} | WGI Port: {self.wgiPort} | XMPP Hostname: {self.xmpp.hostname} | XMPP JID: {self.xmpp.jid} | XMPP password: {self.xmpp.password} | Data: {self.data}"

