# - *- coding: utf- 8 - *-
from os import path
import sqlite3

COLORS = ["#66CDAA", "#1E90FF", "#DAA520", "#8A2BE2", "#800000", "#FFDAB9", "#00FF7F", "#5F9EA0", "#008080", "#2F4F4F", "#556B2F", "#D2B48C", "#B0C4DE", "#F08080", "#FFB6C1", "#EEE8AA", "#00CED1", "#4B0082", "#000080", "#F0FFF0"]

class SensorValueStorage:
    DB_NAME = None

    def __init__(self, databaseName) -> None:
        super().__init__()

        self.DB_NAME = f"{databaseName}.db"

        if not path.exists(self.DB_NAME):
            conn = sqlite3.connect(self.DB_NAME)
            c = conn.cursor()
            c.execute("CREATE TABLE current (sensor text, value real)")
            c.execute("CREATE TABLE voltage (sensor text, value real)")
            conn.commit()
            conn.close()

    def addValue(self, table, sensor, value):
        conn = sqlite3.connect(self.DB_NAME)
        conn.execute(f"INSERT INTO {table} VALUES('{sensor}',{value})")
        conn.commit()
        conn.close()

    def addVoltage(self, sensor, value):
        self.addValue("voltage", sensor, value)

    def addCurrent(self, sensor, value):
        self.addValue("current", sensor, value)

    def fetchGraphData(self, table):
        conn = sqlite3.connect(self.DB_NAME)

        data = {}
        index = 0
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT 300"):
            try:
                sensor = row[0]
                value = row[1]
                data[sensor]["data"].append(value)
            except KeyError:
                data[sensor] = {
                    "label": sensor,
                    "data": [value],
                    "borderColor": COLORS[index%len(COLORS)],
                    "fill": "false"
                }
            index += 1
        conn.close()

        graphData = []
        for key in data:
            data[key]["data"].reverse()
            d = []
            for i in range(0, len(data[key]["data"])):
                d.append({"x": i, "y": data[key]["data"][i]})
            data[key]["data"] = d
            graphData.append(data[key])
        return graphData

    def fetchVoltageGraphData(self):
        return self.fetchGraphData("voltage")

    def fetchCurrentGraphData(self):
        return self.fetchGraphData("current")