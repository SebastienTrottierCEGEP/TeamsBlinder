#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "      Arrêt du serveur Ollama             "
echo "=========================================="

STOPPED=false

# 1. Arrêt via systemd si le service existe et est actif
if command -v systemctl &> /dev/null && systemctl is-active --quiet ollama 2>/dev/null; then
    echo "Arrêt du service systemd 'ollama'..."
    sudo systemctl stop ollama
    STOPPED=true
fi

# 2. Recherche et arrêt des processus 'ollama serve' ou 'ollama'
if pgrep -x "ollama" &> /dev/null; then
    echo "Arrêt des processus Ollama en arrière-plan..."
    pkill -TERM -x "ollama" || true
    
    # Attente gracieuse jusqu'à 5 secondes pour libérer la VRAM et la mémoire
    WAIT_SECS=0
    while pgrep -x "ollama" &> /dev/null && [ $WAIT_SECS -lt 5 ]; do
        sleep 1
        WAIT_SECS=$((WAIT_SECS + 1))
        echo -n "."
    done
    echo ""

    # Si le processus refuse de s'arrêter, forcer l'arrêt (SIGKILL)
    if pgrep -x "ollama" &> /dev/null; then
        echo "Forçage de l'arrêt (SIGKILL)..."
        pkill -KILL -x "ollama" || true
    fi
    STOPPED=true
fi

# 3. Vérification que le port 11434 est bien libéré
if curl -s "http://localhost:11434" &> /dev/null; then
    echo "⚠ Le port 11434 répond toujours."
    echo "Il est possible qu'une instance d'Ollama tourne côté hôte Windows."
else
    if [ "$STOPPED" = true ]; then
        echo "✔ Serveur Ollama arrêté avec succès. Mémoire et VRAM GPU libérées."
    else
        echo "✔ Ollama n'était pas en cours d'exécution dans WSL."
    fi
fi
