# - *- coding: utf- 8 - *-
import time
import sys
import signal
import gpiozero

from spade.agent import Agent
from spade.message import Message
from spade.behaviour import FSMBehaviour, State

from utils.AgentData import AgentData
from utils.WebAppAPI import WebAppAPI

from utils.LocalDB import SensorValueStorage
from utils.MockedSensor import MockedSensor

# Define signal handler to stop agent on remote Raspberry Pi
def signal_term_handler(signal, frame):
    raise KeyboardInterrupt
signal.signal(signal.SIGINT, signal_term_handler)

# Agent data
DB_NAME = "sensor"
storage = SensorValueStorage(DB_NAME)
agentData = AgentData(sys.argv[1]) if len(sys.argv) > 1 else AgentData(data=None, test=True)
webAppAPI = WebAppAPI(agentData.name)

# Load additional data
try:
    DEVICE = agentData.data['DEVICE']
except KeyError:
    webAppAPI.log(f"ERROR: Nije definiran tip uređaja!")
    print("ERROR: Nije definiran tip uređaja!")
    exit(1)

try:
    JUNCTION_BOX_AGENT_JID = f"{agentData.data['JUNCTION_BOX_AGENT_JID']}@{agentData.xmpp.hostname}"
except KeyError:
    webAppAPI.log(f"ERROR: Nije definiran JID agenta razvodne kutije!")
    print("ERROR: Nije definiran JID agenta razvodne kutije!")
    exit(1)

try:
    SERVICE_AGENT_JID = f"{agentData.data['SERVICE_AGENT_JID']}@{agentData.xmpp.hostname}"
except KeyError:
    webAppAPI.log(f"ERROR: Nije definiran JID servisnog agenta!")
    print("ERROR: Nije definiran JID servisnog agenta!")
    exit(1)

try:
    DEVICE_MAX_CURRENT = agentData.data["DEVICE_MAX_CURRENT"]
except KeyError:
    DEVICE_MAX_CURRENT = 30
try:
    MAX_RETRY = agentData.data["MAX_RETRY"]
except KeyError:
    MAX_RETRY = 5
try:
    DEFAULT_TIMEOUT = agentData.data["DEFAULT_TIMEOUT"]
except KeyError:
    DEFAULT_TIMEOUT = 60 * 10 # 10 minutes

# Sensors and pin configuration
relay = gpiozero.OutputDevice(4)
# ampermeterMain = gpiozero.InputDevice(17)
# voltmeterMain = gpiozero.InputDevice(27)

try:
    ampermeterMain = MockedSensor(agentData.data["MOCKED_AMPERMETER_NAME"])
    voltmeterMain = MockedSensor(agentData.data["MOCKED_VOLTMETER_NAME"])
except KeyError:
    ampermeterMain = MockedSensor("device_ampermeter_0001")
    voltmeterMain = MockedSensor("device_voltmeter_0001")

# States
S0 = "S0"
S1 = "S1"
S2 = "S2"
S3 = "S3"
S4 = "S4"
S5 = "S5"
S6 = "S6"
S7 = "S7"

class SensorFSMBehaviour(FSMBehaviour):
    async def on_start(self):
        webAppAPI.log(f"Senzor se pokreće u inicijalnom stanju {self.current_state}")
        print(f"Senzor se pokreće u inicijalnom stanju {self.current_state}")

    async def on_end(self):
        webAppAPI.log(f"Senzor je završio s radom u stanju {self.current_state}")
        print(f"Senzor je završio s radom u stanju {self.current_state}")
        await self.agent.stop()

class StateInitial(State):
    async def run(self):
        #webAppAPI.log("Senzor je u stanju S0: Provjera struje u krugu uređaja")
        #print("Senzor je u stanju S0: Provjera struje u krugu uređaja")
        relay.on()
        voltage = voltmeterMain.getValue()
        if voltage >= 0:
            storage.addVoltage(voltmeterMain.name, voltage)  # Storing value to local DB to diplay it

        current = ampermeterMain.getValue()  # Mocking value from sensor
        if current >= 0:  # If sensor error occurs
            storage.addCurrent(ampermeterMain.name, current)  # Storing value to local DB to diplay it
            if current > DEVICE_MAX_CURRENT:
                relay.off()
                self.set_next_state(S1)
            elif current == 0:
                self.set_next_state(S2)
            else:
                self.set_next_state(S0)

class StateHighCurrent(State):
    async def run(self):
        webAppAPI.log("Senzor je u stanju S1: Prenapon u strujnom krugu")
        print("Senzor je u stanju S1: Prenapon u strujnom krugu")
        self.agent.counterHighCurrent += 1
        if self.agent.counterHighCurrent < MAX_RETRY:
            self.set_next_state(S0)
        else:
            self.set_next_state(S3)

class StateShortCircuit(State):
    async def run(self):
        webAppAPI.log("Senzor je u stanju S3: Na uređaju je kratki spoj! Javljam servisnom agentu.")
        print("Senzor je u stanju S3: Na uređaju je kratki spoj! Javljam servisnom agentu.")

        message = Message(to=SERVICE_AGENT_JID)
        message.body = DEVICE
        message.set_metadata("performative", "malfunction")
        message.set_metadata("ontology", "device")
        await self.send(message)

        response = await self.receive(timeout=DEFAULT_TIMEOUT)
        if response:
            if response.body == "ACCEPTED":
                webAppAPI.log("Servisni centar je obaviješten.")
                print("Servisni centar je obaviješten.")
                self.set_next_state(S7)
            else:
                webAppAPI.log("Niti jedan servisni centar nije prihvatio posao. Gasim agenta.")
                print("Niti jedan servisni centar nije prihvatio posao. Gasim agenta.")
                self.agent.stop()
        else:
            print("Odgovor servisnog agenta nije zaprimljen. Čekam odgovor...\n")
            self.set_next_state(S3)

class StateNoCurrent(State):
    async def run(self):
        webAppAPI.log("Senzor je u stanju S2: Na uređaju nema struje.")
        print("Senzor je u stanju S2: Na uređaju nema struje.")
        self.agent.counterNoCurrent += 1
        voltageTest = voltmeterMain.getValue()
        if voltageTest == 0:
            self.set_next_state(S5)
        elif voltageTest > 0 and self.agent.counterNoCurrent >= MAX_RETRY:
            self.set_next_state(S4)
        else:
            self.set_next_state(S0)

class StateBurnedDevice(State):
    async def run(self):
        webAppAPI.log("Senzor je u stanju S4: Uređaj je pregorio! Javljam servisnom agentu.")
        print("Senzor je u stanju S4: Uređaj je pregorio! Javljam servisnom agentu.")
        message = Message(to=SERVICE_AGENT_JID)
        message.body = DEVICE
        message.set_metadata("performative", "malfunction")
        message.set_metadata("ontology", "device")
        await self.send(message)

        response = await self.receive(timeout=DEFAULT_TIMEOUT)
        if response:
            if response.body == "ACCEPTED":
                webAppAPI.log("Servisni centar je obaviješten.")
                print("Servisni centar je obaviješten.")
                self.set_next_state(S7)
            else:
                webAppAPI.log("Niti jedan servisni centar nije prihvatio posao. Gasim agenta.")
                print("Niti jedan servisni centar nije prihvatio posao. Gasim agenta.")
                await self.agent.stop()
        else:
            print("Odgovor servisnog agenta nije zaprimljen. Čekam odgovor...\n")
            self.set_next_state(S4)


class StateVerifyWithJuncionBox(State):
    async def run(self):
        webAppAPI.log("Senzor je u stanju S5: Provjera struje na glavnom vodu. Javljam agentu razvodne kutije")
        print("Senzor je u stanju S5: Provjera struje na glavnom vodu. Javljam agentu razvodne kutije")

        message = Message(to=JUNCTION_BOX_AGENT_JID)
        message.body = DEVICE
        message.set_metadata("performative", "verification")
        message.set_metadata("ontology", "device")
        await self.send(message)

        confirmation = await self.receive(timeout=DEFAULT_TIMEOUT)
        if confirmation:
            if confirmation.body == "OK":
                webAppAPI.log("Agent razvodne kutije potvrdio je da je napon na razvodnoj kutiji u redu. Postoji problem sa uređajem.")
                print("Agent razvodne kutije potvrdio je da je napon na razvodnoj kutiji u redu. Postoji problem sa uređajem.")
                self.set_next_state(S4)
            else:
                webAppAPI.log("Agent razvodne kutije potvrdio je da na razvodnoj kutiji nema napona. Postoji problem u mreži.")
                print("Agent razvodne kutije potvrdio je da na razvodnoj kutiji nema napona. Postoji problem u mreži.")
                self.set_next_state(S6)
        else:
            print("Odgovor agenta razvodne kutije nije zaprimljen. Čekam odgovor...\n")
            self.set_next_state(S5)

class StateWaitForPower(State):
    async def run(self):
        webAppAPI.log("Senzor je u stanju S6: Čekam na povratak struje u kućnoj mreži")
        print("Senzor je u stanju S6: Čekam na povratak struje u kućnoj mreži")
        time.sleep(60 * 1) # check every minute for power
        self.set_next_state(S5)

class StateWaitForErrorToBeResolved(State):
    async def run(self):
        webAppAPI.log("Senzor je u stanju S7: Čekam na rješavanje problema od strane servisa.")
        print("Senzor je u stanju S7: Čekam na rješavanje problema od strane servisa.")
        confirmation = await self.receive(timeout=DEFAULT_TIMEOUT*100)
        if confirmation:
            if confirmation.body == "CONTINUE":
                webAppAPI.log("Servis je riješio problem sa uređajem. Nastavljam s radom.")
                print("Servis je riješio problem sa uređajem. Nastavljam s radom.")
                self.agent.counterNoCurrent = 0
                self.agent.counterHighCurrent = 0
                self.set_next_state(S0)
            else:
                webAppAPI.log("Servis nije uspio riješiti problem sa uređajem. Gasim agenta.")
                print("Servis nije uspio riješiti problem sa uređajem. Gasim agenta.")
                await self.agent.stop()
        else:
            webAppAPI.log("Odgovor servisa nije zaprimljen. Čekam odgovor...")
            print("Odgovor servisa nije zaprimljen. Čekam odgovor...\n")
            self.set_next_state(S7)


class SensorAgent(Agent):
    counterNoCurrent = 0
    counterHighCurrent = 0

    async def setup(self):
        fsm = SensorFSMBehaviour()
        fsm.add_state(name=S0, state=StateInitial(), initial=True)
        fsm.add_state(name=S1, state=StateHighCurrent())
        fsm.add_state(name=S2, state=StateNoCurrent())
        fsm.add_state(name=S3, state=StateShortCircuit())
        fsm.add_state(name=S4, state=StateBurnedDevice())
        fsm.add_state(name=S5, state=StateVerifyWithJuncionBox())
        fsm.add_state(name=S6, state=StateWaitForPower())
        fsm.add_state(name=S7, state=StateWaitForErrorToBeResolved())
        fsm.add_transition(S0, S0)
        fsm.add_transition(S0, S1)
        fsm.add_transition(S0, S2)

        fsm.add_transition(S1, S0)
        fsm.add_transition(S1, S3)

        fsm.add_transition(S2, S0)
        fsm.add_transition(S2, S4)
        fsm.add_transition(S2, S5)

        fsm.add_transition(S3, S0)
        fsm.add_transition(S3, S3)
        fsm.add_transition(S3, S7)

        fsm.add_transition(S4, S0)
        fsm.add_transition(S4, S4)
        fsm.add_transition(S4, S7)

        fsm.add_transition(S5, S0)
        fsm.add_transition(S5, S4)
        fsm.add_transition(S5, S5)
        fsm.add_transition(S5, S6)

        fsm.add_transition(S6, S5)

        fsm.add_transition(S7, S0)
        fsm.add_transition(S7, S7)

        self.add_behaviour(fsm)

    async def displayChart(self, request):
        db = SensorValueStorage(DB_NAME)
        voltageData = db.fetchVoltageGraphData()
        currentData = db.fetchCurrentGraphData()
        return {"voltageGraphData": voltageData, "currentGraphData": currentData}


if __name__ == "__main__":
    webAppAPI.log(f"Agent starting up... Agent data: {agentData}")
    print(f"{agentData.name} -> Agent starting up... Agent can be stopped with ctrl+C. Agent data: {agentData}")

    sensorAgent = SensorAgent(jid=agentData.xmpp.jid, password=agentData.xmpp.password)
    sensorAgent.start()
    sensorAgent.web.add_get("/graph", sensorAgent.displayChart, "templates/sensorvaluesgraph.html")
    sensorAgent.web.start(hostname="0.0.0.0", port=agentData.wgiPort)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

    sensorAgent.stop()
    webAppAPI.log("Agent je završio s radom.")
    print("Agent je završio s radom.")