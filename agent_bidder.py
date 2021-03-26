# - *- coding: utf- 8 - *-
import sys
import time
import json

import requests
from spade.agent import Agent
from spade.message import Message
from spade.behaviour import OneShotBehaviour
from utils.AgentData import AgentData
from utils.WebAppAPI import WebAppAPI

# Agent data
agentData = AgentData(sys.argv[1]) if len(sys.argv) > 1 else AgentData(data=None, test=True)
webAppAPI = WebAppAPI(agentData.name)

# Load additional data
try:
    SERVICE_CENTRE = agentData.data["SERVICE_CENTRE"]
except KeyError:
    webAppAPI.log(f"ERROR: Podaci servisnog centra su neispravni!")
    print("ERROR: Podaci servisnog centra su neispravni!")
    exit(1)

try:
    SERVICE_AGENT_JID = agentData.data['SERVICE_AGENT_JID']
except KeyError:
    webAppAPI.log(f"ERROR: Nije definiran JID servisnog agenta!")
    print("ERROR: Nije definiran JID servisnog agenta!")
    exit(1)

if "address" not in SERVICE_CENTRE or "street" not in SERVICE_CENTRE["address"] or "city" not in SERVICE_CENTRE["address"]:
    webAppAPI.log(f"ERROR: Servisni centar nema podatke o adresi!")
    print("ERROR: Servisni centar nema podatke o adresi!")
    exit(1)

GOOGLE_MAPS_KEY = "AIzaSyBwWAZCmjJhnzresH7BN8ErhWp0CGeNM34"
GOOGLE_MAPS_URL = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins=Pavlinska ulica 2|Varaždin&destinations={SERVICE_CENTRE['address']['street']}|{SERVICE_CENTRE['address']['city']}&mode=driving&language=hr-HR&units=metric&key={GOOGLE_MAPS_KEY}"

class PrepareBidOfferBehaviour(OneShotBehaviour):
    async def on_start(self):
        webAppAPI.log(f"Zastupam servisni centar - {SERVICE_CENTRE['name']}")
        print(f"Zastupam servisni centar - {SERVICE_CENTRE['name']}")

    async def run(self):
        webAppAPI.log("Pripremam ponudu")
        print("Pripremam ponudu")

        r = requests.get(GOOGLE_MAPS_URL)
        googleMapResponse = r.json()
        distance = {
            "value": 1000000000
        }
        duration = {
            "value": 1000000000
        }
        for element in googleMapResponse["rows"][0]["elements"]:
            if distance is None or element["distance"]["value"] < distance["value"]:
                distance = element["distance"]
            if distance is None or element["duration"]["value"] < duration["value"]:
                duration = element["duration"]

        serviceDuration = int(SERVICE_CENTRE["services"][0]["time"]) * 60
        price = int(SERVICE_CENTRE["services"][0]["price"])

        totalPrice = price + (int(distance["value"]) / 1000) * 2  # 2 kn po km

        score = totalPrice * 100 + serviceDuration  # score = lipe + sekunde

        message = Message(to=SERVICE_AGENT_JID)
        message.set_metadata("performative", "bid")
        message.set_metadata("ontology", "auction")

        scoreInfo = {
            "score": str(score),
            "serviceCentreId": SERVICE_CENTRE["id"]
        }
        message.body = json.dumps(scoreInfo)
        webAppAPI.log(f"SENDING: {message.body} to {SERVICE_AGENT_JID}")
        await self.send(message)

        webAppAPI.log(f"Ponuda servisnog centra - {SERVICE_CENTRE['name']} - je poslana.")
        print(f"Ponuda servisnog centra - {SERVICE_CENTRE['name']} - je poslana.")

    async def on_end(self):
        self.agent.running = False

class AgentBidder(Agent):
    async def setup(self):
        webAppAPI.log(f"Registered agent: {agentData}")
        print(f"Registered agent: {agentData}")
        self.bidBehaviour = PrepareBidOfferBehaviour()
        self.add_behaviour(self.bidBehaviour)


if __name__ == "__main__":
    agent = AgentBidder(jid=agentData.xmpp.jid, password=agentData.xmpp.password)
    agent.running = True
    agent.start()

    while agent.running:
        time.sleep(1)

    agent.bidBehaviour.join(timeout=5)
    agent.stop()

    webAppAPI.log("Agent je završio s radom.")
    print("Agent je završio s radom.")