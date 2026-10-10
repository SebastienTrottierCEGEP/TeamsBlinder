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

# 2. Vérification rapide de l'état d'Ollama
if curl -s "http://localhost:11434" &> /dev/null; then
    echo "✔ Serveur Ollama actif sur http://localhost:11434"
else
    echo "⚠ Serveur Ollama non détecté sur le port 11434."
    echo "  L'anonymisation utilisera le moteur déterministe ou démarrera Ollama."
    echo "  (Pour démarrer Ollama au préalable : ./setup_wsl.sh)"
fi

echo ""

# 3. Lancement du script principal
python3 anonymize_exams.py "$@"
