#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Configuration de l'environnement WSL    "
echo "  Strands Agent SDK + Ollama (llama3.1)  "
echo "=========================================="

# 1. Vérification et configuration du support GPU NVIDIA (CUDA pour WSL2)
echo ""
echo "[1/5] Vérification et configuration du support GPU NVIDIA (CUDA)..."

# Dans WSL2, Windows monte les bibliothèques CUDA dans /usr/lib/wsl/lib
if [ -d "/usr/lib/wsl/lib" ]; then
    export PATH="$PATH:/usr/lib/wsl/lib"

    # Vérification et lien pour libcuda.so
    if [ -f "/usr/lib/wsl/lib/libcuda.so.1" ] && [ ! -e "/usr/lib/wsl/lib/libcuda.so" ]; then
        sudo ln -sf /usr/lib/wsl/lib/libcuda.so.1 /usr/lib/wsl/lib/libcuda.so 2>/dev/null || true
    fi

    # Création de la commande nvidia-smi si absente
    if ! command -v nvidia-smi &> /dev/null; then
        if [ -f "/usr/lib/wsl/lib/nvidia-smi" ]; then
            sudo ln -sf /usr/lib/wsl/lib/nvidia-smi /usr/local/bin/nvidia-smi
        elif command -v nvidia-smi.exe &> /dev/null; then
            sudo tee /usr/local/bin/nvidia-smi > /dev/null << 'EOF'
#!/bin/sh
exec nvidia-smi.exe "$@"
EOF
            sudo chmod +x /usr/local/bin/nvidia-smi
        elif [ -f "/mnt/c/Windows/System32/nvidia-smi.exe" ]; then
            sudo tee /usr/local/bin/nvidia-smi > /dev/null << 'EOF'
#!/bin/sh
exec /mnt/c/Windows/System32/nvidia-smi.exe "$@"
EOF
            sudo chmod +x /usr/local/bin/nvidia-smi
        fi
    fi

    # Enregistrement des librairies CUDA pour le chargeur dynamique (ldconfig)
    if [ ! -f "/etc/ld.so.conf.d/ld.wsl.conf" ] || ! grep -q "/usr/lib/wsl/lib" /etc/ld.so.conf.d/ld.wsl.conf 2>/dev/null; then
        echo "/usr/lib/wsl/lib" | sudo tee /etc/ld.so.conf.d/ld.wsl.conf > /dev/null
        sudo ldconfig
    fi
fi

# Détermination de la commande nvidia-smi à utiliser
GPU_CMD=""
if command -v nvidia-smi &> /dev/null; then
    GPU_CMD="nvidia-smi"
elif command -v nvidia-smi.exe &> /dev/null; then
    GPU_CMD="nvidia-smi.exe"
elif [ -f "/mnt/c/Windows/System32/nvidia-smi.exe" ]; then
    GPU_CMD="/mnt/c/Windows/System32/nvidia-smi.exe"
fi

if [ -n "$GPU_CMD" ]; then
    echo "✔ GPU NVIDIA détecté avec succès via WSL2 :"
    GPU_INFO=$($GPU_CMD --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true)
    if [ -n "$GPU_INFO" ]; then
        while IFS=',' read -r GPU_NAME GPU_VRAM; do
            GPU_NAME_CLEAN="$(echo "${GPU_NAME:-}" | xargs)"
            GPU_VRAM_CLEAN="$(echo "${GPU_VRAM:-}" | xargs)"
            echo "   • Carte vidéo : $GPU_NAME_CLEAN"
            echo "   • VRAM totale : $GPU_VRAM_CLEAN"
        done <<< "$GPU_INFO"
    else
        $GPU_CMD
    fi
elif [ -f "/usr/lib/wsl/lib/libcuda.so.1" ]; then
    echo "✔ Bibliothèque CUDA (/usr/lib/wsl/lib/libcuda.so.1) détectée !"
    echo "  Ollama pourra utiliser l'accélération GPU CUDA."
else
    echo "⚠ Commande 'nvidia-smi' non détectée."
    if [ ! -e "/dev/dxg" ]; then
        echo "  Notice : Le pont DirectX / GPU (/dev/dxg) n'est pas présent dans WSL2."
        echo "  Pour l'activer, exécutez sous Windows (PowerShell en admin) :"
        echo "    wsl --update"
        echo "    wsl --shutdown"
        echo "  et vérifiez que vos pilotes NVIDIA GeForce / Studio sont installés sous Windows."
    else
        echo "  Ollama utilisera le CPU sauf si le support CUDA WSL2 est activé."
    fi
fi

# 2. Vérification des prérequis système
echo ""
echo "[2/5] Vérification des outils système (curl, zstd, tar, python3, venv)..."
MISSING_PKGS=()
for pkg in curl zstd tar python3; do
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
echo "[3/5] Vérification d'Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "Installation d'Ollama via le script officiel..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "✔ Ollama est déjà installé : $(ollama --version)"
fi

# 4. Préparation de l'environnement virtuel Python
echo ""
echo "[4/5] Mise en place de l'environnement virtuel Python (.venv)..."
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
echo "[5/5] Vérification et démarrage du service Ollama..."
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

# Lecture du modèle depuis config.properties s'il existe
TARGET_MODEL="llama3.1"
if [ -f "config.properties" ]; then
    CONF_MODEL=$(grep -E '^[[:space:]]*model_id[[:space:]]*=' config.properties | cut -d'=' -f2 | xargs || true)
    if [ -n "$CONF_MODEL" ]; then
        TARGET_MODEL="$CONF_MODEL"
    fi
fi

# Téléchargement du modèle sélectionné
echo "Téléchargement du modèle '$TARGET_MODEL' (si non présent)..."
ollama pull "$TARGET_MODEL"

echo ""
echo "=========================================="
echo "✔ Configuration terminée avec succès !"
echo "=========================================="
echo "Commandes disponibles :"
echo "  - Anonymiser les examens : ./run_anonymizer.sh"
echo "  - Gérer les modèles      : ./manage_models.sh"
echo "  - Arrêter Ollama         : ./stop_ollama.sh"
echo ""
