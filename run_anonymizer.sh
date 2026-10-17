#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "      Lancement de TeamsBlinder           "
echo "  Anonymisation des examens étudiants     "
echo "=========================================="

# 1. Activation de l'environnement virtuel Python s'il existe
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# 2. Vérification de l'état d'Ollama (lecture de l'hôte dans config.properties si configuré)
OLLAMA_HOST="http://localhost:11434"
if [ -f "config.properties" ]; then
    CONF_HOST=$(grep -E '^[[:space:]]*host[[:space:]]*=' config.properties | cut -d'=' -f2- | tr -d ' \r\n' || true)
    if [ -n "$CONF_HOST" ]; then
        OLLAMA_HOST="$CONF_HOST"
    fi
fi

if ! curl -s --max-time 3 -f "${OLLAMA_HOST}/api/version" &> /dev/null && ! curl -s --max-time 3 -f "${OLLAMA_HOST}" &> /dev/null; then
    echo "❌ ERREUR : Le serveur Ollama ne répond pas sur ${OLLAMA_HOST}."
    echo "   L'anonymisation ne doit pas être tentée si Ollama ne répond pas."
    echo "   Veuillez démarrer Ollama (ex: ./setup_wsl.sh ou 'ollama serve') avant de lancer l'anonymisation."
    exit 1
fi

echo "✔ Serveur Ollama actif et joignable sur ${OLLAMA_HOST}"

echo ""

# 3. Lancement du script principal
python3 anonymize_exams.py "$@"
