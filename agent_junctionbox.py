# - *- coding: utf- 8 - *-
import time
import sys
import signal

import asyncio
import gpiozero
from spade.agent import Agent
from spade.message import Message
from spade.behaviour import CyclicBehaviour
from spade.template import Template

from utils.MockedSensor import MockedSensor
from utils.LocalDB import SensorValueStorage
from utils.AgentData import AgentData
from utils.WebAppAPI import WebAppAPI
from utils import DateTimeUtils

# Define signal handler to stop agent on remote Raspberry Pi
def signal_term_handler(signal, frame):
    raise KeyboardInterrupt
signal.signal(signal.SIGINT, signal_term_handler)

# Agent data
DB_NAME = "junctionbox"
storage = SensorValueStorage(DB_NAME)
agentData = AgentData(sys.argv[1]) if len(sys.argv) > 1 else AgentData(data=None, test=True)
webAppAPI = WebAppAPI(agentData.name)

# Load additional data
try:
    DEFAULT_TIMEOUT = agentData.data["DEFAULT_TIMEOUT"]
except KeyError:
    DEFAULT_TIMEOUT = 60 * 10 # 10min

# Sensors and pin configuration
relays = []
voltmeters = []
ampermeters = []
try:
    relays.append(gpiozero.OutputDevice(21))
    relays.append(gpiozero.OutputDevice(20))
    relays.append(gpiozero.OutputDevice(16))
    relays.append(gpiozero.OutputDevice(26))
    relays.append(gpiozero.OutputDevice(19))
    relays.append(gpiozero.OutputDevice(13))
    relays.append(gpiozero.OutputDevice(6))
    relays.append(gpiozero.OutputDevice(5))
except:
    webAppAPI.log("GPIO Nije omogućen na ovom uređaju! Kopirajte skriptu na RPi.")
    pass

for i in range(0, 9):
    voltmeters.append(MockedSensor(f"junctionbox_voltmeter_000{i}"))
    ampermeters.append(MockedSensor(f"junctionbox_ampermeter_000{i}"))


class JunctionBoxAgent(Agent):
    async def setup(self):
        webAppAPI.log(f"Registered agent: {agentData}")
        print(f"Registered agent: {agentData}")
        checkFromDeviceTemplate = Template()
        checkFromDeviceTemplate.set_metadata("performative", "verification")
        checkFromDeviceTemplate.set_metadata("ontology", "device")
        self.add_behaviour(self.MessageListeningBehaviour(), template=checkFromDeviceTemplate)
        self.add_behaviour(self.LogValuesToLocalDatabaseBehaviour())

    async def displayChart(self, request):
        db = SensorValueStorage(DB_NAME)
        voltageData = db.fetchVoltageGraphData()
        currentData = db.fetchCurrentGraphData()
        return {"voltageGraphData": voltageData, "currentGraphData": currentData}

    class MessageListeningBehaviour(CyclicBehaviour):
        async def run(self):
            print("Čekam poruku...")
            message = await self.receive(timeout=DEFAULT_TIMEOUT)
            if message:
                reply = Message(to=str(message.sender))
                reply.set_metadata("performative", "confirmation")
                reply.set_metadata("ontology", "device")

                status = True
                for voltmeter in voltmeters:
                    voltage = voltmeter.getValue()
                    status = status and voltage > 200 and voltage < 250

                reply.body = "OK" if status else "ERROR"
                await self.send(reply)
            else:
                print(f"Nije bilo upita u posljednjih {DateTimeUtils.secondsToHumanTime(DEFAULT_TIMEOUT)}")

    class LogValuesToLocalDatabaseBehaviour(CyclicBehaviour):
        async def run(self):
            for v in voltmeters:
                voltage = v.getValue()
                if voltage >= 0:
                    storage.addVoltage(v.name, voltage)

            for i in range(0, len(ampermeters)):
                current = ampermeters[i].getValue()
                if current > 1000: # 1A is allowed for each line
                    try:
                        relays[i].off()
                    except IndexError:
                        pass # GPIO Nije omogućen na ovom uređaju!
                else:
                    try:
                        relays[i].on()
                    except IndexError:
                        pass  # GPIO Nije omogućen na ovom uređaju!

                if current >= 0:
                    storage.addCurrent(ampermeters[i].name, current)
            await asyncio.sleep(1)


if __name__ == "__main__":
    webAppAPI.log(f"Agent starting up... Agent data: {agentData}")
    print(f"Agent starting up... Agent can be stopped with ctrl+C. Agent data: {agentData}")

    junctionBoxAgent = JunctionBoxAgent(jid=agentData.xmpp.jid, password=agentData.xmpp.password)
    junctionBoxAgent.start()
    junctionBoxAgent.web.add_get("/graph", junctionBoxAgent.displayChart, "templates/sensorvaluesgraph.html")
    junctionBoxAgent.web.start(hostname="0.0.0.0", port=agentData.wgiPort)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

    junctionBoxAgent.stop()

    webAppAPI.log("Agent je završio s radom.")
    print("Agent je završio s radom.")
