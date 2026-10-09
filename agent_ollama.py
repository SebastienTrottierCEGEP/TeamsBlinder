import sys
import time
from typing import Any
from strands import Agent
from strands.models.ollama import OllamaModel


class ConsoleProgressHandler:
    """Affiche en temps réel le flux et la progression de l'agent dans la console."""

    def __init__(self):
        self.started = False
        self.start_time = None
        self.chunk_count = 0

    def __call__(self, **kwargs: Any) -> None:
        # Étape initiale : premier chunk reçu
        if not self.started and "data" in kwargs:
            self.started = True
            self.start_time = time.time()
            print("\n[Progression] Génération en cours...")
            print("─" * 50)

        # Flux de texte en continu (token par token / mot par mot)
        if "data" in kwargs and kwargs["data"]:
            self.chunk_count += 1
            print(kwargs["data"], end="", flush=True)

        # Affichage du raisonnement si le modèle en produit (thinking/reasoning)
        if kwargs.get("reasoningText"):
            print(f"\n[Raisonnement] {kwargs['reasoningText']}", flush=True)

        # Signal de fin de génération
        if kwargs.get("complete"):
            elapsed = time.time() - (self.start_time or time.time())
            print("\n" + "─" * 50)
            print(f"✔ Terminé en {elapsed:.2f}s ({self.chunk_count} chunks reçus).\n")


def main():
    # Configuration du modèle local Ollama
    # STROTTIER llama3.1 lourd pour 4GB VRAM
    model = OllamaModel(host="http://localhost:11434", model_id="llama3.1")

    # Gestionnaire de progression en direct
    progress_handler = ConsoleProgressHandler()

    # Initialisation de l'agent avec le gestionnaire de progression
    agent = Agent(model=model, callback_handler=progress_handler)

    # Prompt par défaut ou passé en argument CLI
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What is an agent harness, in one sentence?"
    print(f"Question : {prompt}")

    # Exécution de l'agent
    agent(prompt)


if __name__ == "__main__":
    main()
