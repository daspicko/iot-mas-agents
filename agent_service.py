# - *- coding: utf- 8 - *-
import subprocess
import time
import sys
import signal
import base64

import json

from utils.AgentData import AgentData

from spade.agent import Agent
from spade.message import Message
from spade.template import Template
from spade.behaviour import CyclicBehaviour, OneShotBehaviour

from utils import DateTimeUtils
from utils.WebAppAPI import WebAppAPI
from utils.WebAppAPI import WebAppServicesAPI

# Define signal handler to stop agent on remote Raspberry Pi
def signal_term_handler(signal, frame):
    raise KeyboardInterrupt
signal.signal(signal.SIGINT, signal_term_handler)

# Agent data
agentData = AgentData(sys.argv[1]) if len(sys.argv) > 1 else AgentData(data=None, test=True)
webAppAPI = WebAppAPI(agentData.name)
webAppServicesAPI = WebAppServicesAPI()

# Load additional data
try:
    SERVICE_AGENT_MESSAGE_TIMEOUT = agentData.data["SERVICE_AGENT_MESSAGE_TIMEOUT"]
except KeyError:
    SERVICE_AGENT_MESSAGE_TIMEOUT = 60 * 60 * 24 # 1 day

try:
    AUCTION_DURATION = agentData.data["AUCTION_DURATION"]
except KeyError:
    AUCTION_DURATION = 10 # 10 sec

class ReceiveSensorMessagesBehaviour(CyclicBehaviour):
    async def run(self):
        message = await self.receive(timeout=SERVICE_AGENT_MESSAGE_TIMEOUT)

        if message:
            webAppAPI.log(f"Zaprimljena je poruka od agenta senzora {str(message.sender)}")
            print(f"Zaprimljena je poruka od agenta senzora {str(message.sender)}")
            self.agent.sensorAgent = str(message.sender)
            self.agent.deviceName = message.body

            serviceCenters = webAppServicesAPI.getAllServicesForDevice(self.agent.deviceName)
            for serviceCentre in serviceCenters:
                for service in serviceCentre["services"]:
                    if service["device"]["name"].lower() != self.agent.deviceName.lower():
                        serviceCentre["services"].remove(service)
            self.agent.serviceCentres = serviceCenters
            self.agent.offers = []

            self.agent.isAuctionStarted = True
            self.agent.auctionTimeout = AUCTION_DURATION
            for serviceCentre in self.agent.serviceCentres:
                bidderAgentData = {
                    "name": f"Bidder agent | {serviceCentre['name']}",
                    "xmpp": {
                        "hostname": agentData.xmpp.hostname,
                        "jid": f"agent-bidder-{serviceCentre['id']}",
                        "password": "0000"
                    },
                    "data": {
                        "SERVICE_CENTRE": serviceCentre,
                        "SERVICE_AGENT_JID": agentData.xmpp.jid
                    }
                }
                bidderAgentDataEncoded = base64.b64encode(json.dumps(bidderAgentData).encode('utf-8')).decode()
                subprocess.run(f"docker run --rm -d --network host -v $(pwd):/opt/iot-mas/agents -w /opt/iot-mas/agents daspicko/spade:1.0 python3 agent_bidder.py {bidderAgentDataEncoded}", shell=True)
                #subprocess.run(f"python3 agent_bidder.py {bidderAgentDataEncoded}", shell=True)
        else:
            webAppAPI.log(f"Nije bilo upita u posljednjih {DateTimeUtils.secondsToHumanTime(SERVICE_AGENT_MESSAGE_TIMEOUT)}")
            print(f"Nije bilo upita u posljednjih {DateTimeUtils.secondsToHumanTime(SERVICE_AGENT_MESSAGE_TIMEOUT)}")


class ReceiveBidderMessagesBehaviour(CyclicBehaviour):
    async def run(self):
        message = await self.receive(timeout=1)

        if message:
            print(f"primljena je poruka {message.body}")
            msg = json.loads(message.body)
            self.agent.offers.append(msg)
        else:
            if self.agent.isAuctionStarted:
                self.agent.auctionTimeout -= 1

                if self.agent.auctionTimeout <= 0 or len(self.agent.offers) == len(self.agent.serviceCentres):
                    self.agent.isAuctionStarted = False
                    if self.agent.determineAuctionWinnerBehaviour is None:
                        self.agent.determineAuctionWinnerBehaviour = DetermineAuctionWinnerBehaviour()
                        self.agent.add_behaviour(self.agent.determineAuctionWinnerBehaviour)
                    else:
                        self.agent.determineAuctionWinnerBehaviour.start()

class DetermineAuctionWinnerBehaviour(OneShotBehaviour):
    async def on_start(self):
        webAppAPI.log(f"Broj servisa: {len(self.agent.serviceCentres)}, Broj pristiglih ponuda: {len(self.agent.offers)}")
        print(f"Broj servisa: {len(self.agent.serviceCentres)}, Broj pristiglih ponuda: {len(self.agent.offers)}")

    async def run(self):
        if len(self.agent.offers) > 0:
            bestOffer = None
            for offer in self.agent.offers:
                if bestOffer is None or bestOffer["score"] < offer["score"]:
                    bestOffer = offer
            self.agent.bestOffer = bestOffer
        else:
            self.agent.bestOffer = None

    async def on_end(self):
        if self.agent.bestOffer is not None:
            webAppAPI.log("Pronađena je najbolja ponuda.")
            print("Pronađena je najbolja ponuda.")
            serviceCentreId = self.agent.bestOffer["serviceCentreId"]
            for serviceCentre in self.agent.serviceCentres:
                if serviceCentre["id"] == serviceCentreId:
                    webAppAPI.sendEmail(serviceCentre["contact"]["email"], f"Poštovani, potrebna je usluga servisa za {self.agent.deviceName}. Vaša ponuda je pobijedila na aukciji sa {self.agent.bestOffer['score']}.")

                    message = Message(to=self.agent.sensorAgent)
                    message.body = "ACCEPTED"
                    message.set_metadata("performative", "service")
                    message.set_metadata("ontology", "device")
                    await self.send(message)
                    break
        else:
            webAppAPI.log("Ne postoji ponuda za servis uređaja!")
            print("Ne postoji ponuda za servis uređaja!")
            webAppAPI.sendEmail("daspicko@foi.hr", f"Nema ponude za servis uređaja {self.agent.deviceName}")
            message = Message(to=self.agent.sensorAgent)
            message.body = "NOT ACCEPTED"
            message.set_metadata("performative", "service")
            message.set_metadata("ontology", "device")
            await self.send(message)


class ServiceAgent(Agent):
    deviceName = ""
    serviceCentres = []
    offers = []
    determineAuctionWinnerBehaviour = None
    isAuctionStarted = False
    auctionTimeout = AUCTION_DURATION

    async def setup(self):
        sensorMessageTemplate = Template()
        sensorMessageTemplate.set_metadata("performative", "malfunction")
        sensorMessageTemplate.set_metadata("ontology", "device")
        self.add_behaviour(ReceiveSensorMessagesBehaviour(), template=sensorMessageTemplate)

        bidMessageTemplate = Template()
        bidMessageTemplate.set_metadata("performative", "bid")
        bidMessageTemplate.set_metadata("ontology", "auction")
        self.add_behaviour(ReceiveBidderMessagesBehaviour(), template=bidMessageTemplate)


    async def on_start(self):
        webAppAPI.log("Servisni agent je pokrenut.")
        print(f"Servisni agent je pokrenut")

    async def on_end(self):
        webAppAPI.log(f"Servisni agent završava s radom")
        print(f"Servisni agent završava s radom")


if __name__ == "__main__":
    webAppAPI.log(f"Agent starting up... Agent can be stopped with ctrl+C. Agent data: {agentData}")
    print(f"{agentData.name} -> Agent starting up... Agent can be stopped with ctrl+C. Agent data: {agentData}")

    serviceAgent = ServiceAgent(jid=agentData.xmpp.jid, password=agentData.xmpp.password)
    serviceAgent.start()
    serviceAgent.web.start(hostname="0.0.0.0", port=agentData.wgiPort)

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

    serviceAgent.stop()

    webAppAPI.log("Servisni agent je završio s radom.")
    print("Servisni agent je završio s radom.")
