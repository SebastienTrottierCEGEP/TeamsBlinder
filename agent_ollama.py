from strands import Agent
from strands.models.ollama import OllamaModel

# Initialisation du modèle Ollama local
model = OllamaModel(host="http://localhost:11434", model_id="llama3.1")

# Initialisation de l'agent
agent = Agent(model=model)

# Exécution de la requête
response = agent("What is an agent harness, in one sentence?")
print(response)
