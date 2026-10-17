#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Activation de l'environnement virtuel Python s'il existe
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# 2. Vérification des arguments
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <fichier_a_deanonymiser> [-o <fichier_sortie>] [-m <mapping_central.csv>] [--append-da]"
    echo ""
    echo "Exemple :"
    echo "  $0 notes_examen.csv"
    echo "  -> Génère : notes_examen_out.csv avec les vrais noms et DA"
    exit 1
fi

# 3. Lancement du script Python de dé-anonymisation
python3 deanonymize.py "$@"
