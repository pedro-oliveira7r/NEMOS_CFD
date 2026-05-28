import Agent_1

case_path = r"C:\Users\pedro\Desktop\TCC1\TESTS"

case = "The problem consists of a small meeting room that is 3x3x3 meters, " \
"two people seat at small meeting table in the center of the room. " \
"There is an air conditioning unit..."

agent = Agent_1.SimulationAgent(case, case_path)
agent.start()