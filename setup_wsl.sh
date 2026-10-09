#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Configuration de l'environnement WSL    "
echo "  Strands Agent SDK + Ollama (llama3.1)  "
echo "=========================================="

# 1. Vérification du GPU / NVIDIA CUDA
echo ""
echo "[1/6] Vérification du support GPU NVIDIA (CUDA)..."
if command -v nvidia-smi &> /dev/null; then
    echo "✔ GPU NVIDIA détecté avec succès :"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || nvidia-smi
else
    echo "⚠ Commande 'nvidia-smi' non détectée."
    echo "  Ollama utilisera le CPU sauf si le support CUDA WSL2 est activé ultérieurement."
fi

# 2. Vérification des prérequis système
echo ""
echo "[2/6] Vérification des outils système (curl, python3, venv)..."
MISSING_PKGS=()
for pkg in curl python3; do
    if ! command -v "$pkg" &> /dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done

if ! python3 -c "import venv" &> /dev/null; then
    MISSING_PKGS+=("python3-venv")
fi

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "Installation des dépendances manquantes : ${MISSING_PKGS[*]}"
    sudo apt-get update && sudo apt-get install -y "${MISSING_PKGS[@]}"
else
    echo "✔ Outils système requis présents."
fi

# 3. Vérification / Installation de Ollama
echo ""
echo "[3/6] Vérification d'Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "Installation d'Ollama via le script officiel..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "✔ Ollama est déjà installé : $(ollama --version)"
fi

# 4. Préparation de l'environnement virtuel Python
echo ""
echo "[4/6] Mise en place de l'environnement virtuel Python (.venv)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✔ Environnement virtuel .venv créé."
fi

source .venv/bin/activate
pip install --upgrade pip --quiet
echo "Installation de strands-agents[ollama]..."
pip install 'strands-agents[ollama]' --quiet
echo "✔ Dépendances Python installées avec succès."

# 5. Démarrage du serveur Ollama et attente
echo ""
echo "[5/6] Vérification et démarrage du service Ollama..."
is_ollama_running() {
    curl -s -f "http://localhost:11434" &> /dev/null
}

if is_ollama_running; then
    echo "✔ Le serveur Ollama est déjà actif sur http://localhost:11434"
else
    echo "Démarrage du serveur Ollama..."
    if command -v systemctl &> /dev/null && systemctl is-system-running &> /dev/null; then
        sudo systemctl start ollama || true
    fi

    if ! is_ollama_running; then
        nohup ollama serve > ollama.log 2>&1 &
        OLLAMA_PID=$!
        echo "Serveur Ollama lancé en tâche de fond (PID: $OLLAMA_PID, logs: ollama.log)"
    fi

    # Attente de disponibilité (jusqu'à 30 secondes)
    WAIT_COUNT=0
    until is_ollama_running || [ $WAIT_COUNT -ge 30 ]; do
        sleep 1
        WAIT_COUNT=$((WAIT_COUNT + 1))
        echo -n "."
    done
    echo ""

    if is_ollama_running; then
        echo "✔ Serveur Ollama prêt !"
    else
        echo "❌ Impossible de contacter le serveur Ollama après 30s. Consultez ollama.log."
        exit 1
    fi
fi

# Téléchargement du modèle llama3.1
echo "Téléchargement du modèle llama3.1 (si non présent)..."
ollama pull llama3.1

# 6. Exécution du programme Python
echo ""
echo "[6/6] Exécution de agent_ollama.py..."
echo "------------------------------------------"
python agent_ollama.py
echo "------------------------------------------"
echo ""
echo "✔ Exécution terminée avec succès !"
