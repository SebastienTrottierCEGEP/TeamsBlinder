# Strands Agent SDK avec Ollama (WSL2 / GPU CUDA)

Ce projet configure et exécute un agent basé sur **Strands Agent SDK** utilisant un modèle local **Ollama** (`llama3.1`) avec accélération GPU NVIDIA sous WSL.

---

## Structure des fichiers

- **`agent_ollama.py`** : Programme Python minimal utilisant `Strands Agent SDK` et `OllamaModel`.
- **`setup_wsl.sh`** : Script d'installation et de démarrage automatisé sous WSL.
- **`requirements.txt`** : Dépendances Python (`strands-agents[ollama]`).

---

## Instructions d'exécution sous WSL

### 1. Ouvrir votre terminal WSL
Rendez-vous dans le répertoire du projet :
```bash
cd /mnt/z/home/strottier/repos/TeamsBlinder
# ou le chemin correspondant dans votre distribution WSL
```

### 2. Rendre le script exécutable et le lancer
```bash
chmod +x setup_wsl.sh
./setup_wsl.sh
```

Le script s'occupe de :
1. Détecter votre carte graphique NVIDIA et le support CUDA via `nvidia-smi`.
2. Installer les paquets système nécessaires (`curl`, `python3-venv`).
3. Installer `ollama` si ce n'est pas déjà fait.
4. Créer un environnement virtuel Python (`.venv`) et installer `strands-agents[ollama]`.
5. Démarrer `ollama serve` et attendre qu'il soit opérationnel sur le port `11434`.
6. Télécharger le modèle `llama3.1` (`ollama pull llama3.1`).
7. Exécuter `agent_ollama.py` et afficher la réponse de l'agent.

---

## Exécutions ultérieures

Une fois l'installation terminée, vous pouvez relancer le script Python directement :

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Lancer l'agent
python agent_ollama.py
```
