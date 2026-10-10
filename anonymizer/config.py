"""
Module de configuration pour TeamsBlinder.
Charge et valide les propriétés depuis config.properties.
"""

import os
from typing import Dict, Any


def load_config(filepath: str = "config.properties") -> Dict[str, Any]:
    """
    Charge les propriétés depuis un fichier clé=valeur (ex: config.properties).
    Résout les chemins relatifs par rapport au dossier racine du projet.
    """
    props = {
        "model_id": "llama3.2:3b",
        "host": "http://localhost:11434",
        "agent_max_turns": "30",
        "agent_max_tool_calls": "60",
        "agent_max_repeated_calls": "3",
        "submissions_base_path": "./SampleDir",
        "exam_name": "Objets Connectés 1 - Examen 1",
        "anonymized_base_path": "./SampleDir_Anonymise",
        "replacement_prefix": "etudiant",
        "mapping_file": "./SampleDir_Anonymise/mapping_central.csv",
    }

    # Recherche dans le dossier parent si le chemin est relatif
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = os.path.join(base_dir, filepath) if not os.path.isabs(filepath) else filepath

    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    props[key.strip()] = val.strip()

    # Normalisation des chemins absolus
    for path_key in ["submissions_base_path", "anonymized_base_path", "mapping_file"]:
        val = props.get(path_key, "")
        if val and not os.path.isabs(val):
            props[path_key] = os.path.normpath(os.path.join(base_dir, val))

    return props
