# Strands Agent SDK avec Ollama (WSL2 / GPU CUDA)

Ce projet configure et exécute un agent basé sur **Strands Agent SDK** utilisant un modèle local **Ollama** (`llama3.1`) avec accélération GPU NVIDIA sous WSL.

---

## Structure des fichiers

- **`config.properties`** : Fichier de propriétés pour configurer le nom du modèle (`model_id`) et l'hôte (`host`).
- **`agent_ollama.py`** : Programme Python minimal utilisant `Strands Agent SDK` et `OllamaModel`.
- **`ollama_tui.py`** : Application TUI interactive pour lister, sélectionner et supprimer les modèles Ollama locaux.
- **`manage_models.sh`** : Raccourci bash pour lancer rapidement l'application TUI.
- **`setup_wsl.sh`** : Script d'installation et de démarrage automatisé sous WSL.
- **`stop_ollama.sh`** : Script pour arrêter proprement Ollama et libérer la VRAM / mémoire.
- **`enable_cuda_wsl.sh`** : Script dédié d'activation et diagnostic du GPU NVIDIA CUDA sous WSL2.
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
6. Télécharger le modèle configuré dans `config.properties` (ex: `llama3.1`).
7. Exécuter `agent_ollama.py` et afficher la réponse de l'agent.

---

## Configuration du modèle (`config.properties`)

Vous pouvez changer le modèle utilisé sans toucher au code Python en éditant `config.properties` :

```properties
# Nom du modèle Ollama à utiliser
model_id=llama3.1

# URL de l'hôte Ollama
host=http://localhost:11434
```

*Modèles recommandés selon votre configuration GPU (ex: 4GB VRAM) :*
- `llama3.2:1b` (~1.3 Go)
- `llama3.2:3b` (~2.0 Go)
- `phi3:mini` (~2.3 Go)
- `qwen2.5:1.5b` (~1.0 Go)
- `qwen2.5:3b` (~2.0 Go)
- `llama3.1` (8B, ~4.7 Go)

Vous pouvez également choisir le modèle actif directement dans l'interface TUI (`./manage_models.sh`) avec la touche **`[Entrée]`** ou **`[s]`**.

---

## Exécutions ultérieures

Une fois l'installation terminée, vous pouvez relancer le script Python directement :

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Lancer l'agent
python agent_ollama.py
```

---

## Arrêter Ollama (libérer GPU et mémoire)

Pour stopper le serveur Ollama lorsqu'il n'est plus utilisé :

```bash
chmod +x stop_ollama.sh
./stop_ollama.sh
```

---

## Gestionnaire de modèles (Interface TUI)

Pour afficher tous les modèles locaux téléchargés et en supprimer facilement :

```bash
chmod +x manage_models.sh
./manage_models.sh
# ou directement : python3 ollama_tui.py
```

**Raccourcis clavier :**
- `↑` / `↓` ou `k` / `j` : Naviguer dans la liste
- `d` ou `Suppr` : Supprimer le modèle sélectionné (avec confirmation)
- `r` : Rafraîchir la liste
- `q` ou `Échap` : Quitter


