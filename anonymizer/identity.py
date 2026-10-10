"""
Module d'extraction et de gestion des identités étudiantes.
Permet d'extraire le nom et le DA (7 chiffres), et de consigner la correspondance
dans un fichier central de traçabilité (mapping_central.csv).
"""

import csv
import datetime
import os
import re
from typing import Dict, Optional, Tuple


def extract_student_identity(folder_name: str) -> Tuple[str, str]:
    """
    Extrait le nom complet et le DA (numéro à 7 chiffres) depuis le nom du dossier étudiant.
    Exemples supportés :
      - 'Gaetan Simard (2244612)' -> ('Gaetan Simard', '2244612')
      - 'Simard, Gaetan (2244612)' -> ('Simard, Gaetan', '2244612')
      - 'Gaetan Simard_2244612'   -> ('Gaetan Simard', '2244612')
      - 'Gaetan Simard'            -> ('Gaetan Simard', '')
    """
    cleaned = folder_name.strip()

    # 1. Format principal Teams : "Nom Étudiant (1234567)"
    m = re.match(r"^(.*?)\s*\(\s*(\d{7})\s*\)$", cleaned)
    if m:
        name = m.group(1).strip()
        da = m.group(2).strip()
        return name, da

    # 2. Format avec tiret ou underscore : "Nom Étudiant_1234567" ou "Nom Étudiant - 1234567"
    m = re.match(r"^(.*?)[_\s-]+(\d{7})$", cleaned)
    if m:
        name = m.group(1).strip()
        da = m.group(2).strip()
        return name, da

    # 3. Présence d'un numéro de 7 chiffres n'importe où
    m_da = re.search(r"\b(\d{7})\b", cleaned)
    if m_da:
        da = m_da.group(1)
        name = cleaned.replace(da, "").strip(" ()_-")
        return name, da

    # 4. Aucun DA trouvé dans le titre du dossier
    return cleaned, ""


class MappingTracker:
    """
    Gère le fichier central de correspondance entre l'identité originale et le pseudonyme.
    """

    CSV_HEADERS = [
        "alias",
        "student_name",
        "da",
        "source_folder",
        "destination_folder",
        "exam_name",
        "timestamp",
    ]

    def __init__(self, mapping_file_path: str, prefix: str = "etudiant"):
        self.mapping_file_path = os.path.abspath(mapping_file_path)
        self.prefix = prefix
        self.mappings: Dict[str, Dict[str, str]] = {}  # clé : (student_name, da) -> record
        self._load_existing_mapping()

    def _load_existing_mapping(self) -> None:
        """Charge le mapping existant pour préserver les pseudonymes déjà attribués."""
        if os.path.exists(self.mapping_file_path):
            try:
                with open(self.mapping_file_path, "r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        key = (row.get("student_name", ""), row.get("da", ""))
                        self.mappings[key] = row
            except Exception as e:
                print(f"⚠ Attention : impossible de lire le mapping existant ({e})")

    def get_or_create_alias(
        self,
        student_name: str,
        da: str,
        source_folder: str,
        destination_folder: str,
        exam_name: str,
    ) -> str:
        """
        Retourne l'alias existant ou en crée un nouveau incrémental (ex: etudiant01).
        """
        key = (student_name, da)
        if key in self.mappings:
            return self.mappings[key]["alias"]

        # Déterminer le prochain index disponible
        used_indices = set()
        for record in self.mappings.values():
            alias_str = record.get("alias", "")
            if alias_str.startswith(self.prefix):
                try:
                    num = int(alias_str[len(self.prefix):])
                    used_indices.add(num)
                except ValueError:
                    pass

        next_index = 1
        while next_index in used_indices:
            next_index += 1

        new_alias = f"{self.prefix}{next_index:02d}"

        record = {
            "alias": new_alias,
            "student_name": student_name,
            "da": da,
            "source_folder": os.path.abspath(source_folder),
            "destination_folder": os.path.abspath(destination_folder),
            "exam_name": exam_name,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.mappings[key] = record
        self._save_mappings()
        return new_alias

    def _save_mappings(self) -> None:
        """Enregistre l'ensemble des correspondances dans le fichier CSV."""
        os.makedirs(os.path.dirname(self.mapping_file_path), exist_ok=True)
        with open(self.mapping_file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
            writer.writeheader()
            for record in sorted(self.mappings.values(), key=lambda r: r.get("alias", "")):
                writer.writerow(record)
