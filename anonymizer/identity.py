"""
Module d'extraction et de gestion des identités étudiantes.
Permet d'extraire le nom et le DA (7 chiffres), et de consigner la correspondance
dans un fichier central de traçabilité (mapping_central.csv).
"""

import csv
import datetime
import os
import re
import unicodedata
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


def normalize_for_sort(text: str) -> str:
    """Supprime les accents et convertit en minuscules pour un tri alphabétique robuste."""
    nfkd = unicodedata.normalize("NFKD", text)
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    return clean.lower().strip()


def split_first_last_name(student_name: str) -> Tuple[str, str]:
    """
    Extrait (nom_de_famille, prenoms) pour le tri alphabétique selon la convention Teams.
    Gère les noms simples, les noms composés, avec particules et les formats 'Nom, Prénom'.
    """
    cleaned = student_name.strip()
    if "," in cleaned:
        parts = cleaned.split(",", 1)
        return parts[0].strip(), parts[1].strip()

    tokens = cleaned.split()
    if len(tokens) == 0:
        return "", ""
    if len(tokens) == 1:
        return tokens[0], ""
    if len(tokens) == 2:
        return tokens[1], tokens[0]

    particles = {"de", "du", "des", "le", "la", "van", "von", "da", "di", "del", "della"}

    # 4 composantes (ex: Jordan Avery Pierre Stone, Robin Casey Willow Birch)
    if len(tokens) == 4:
        if tokens[2].lower() in particles:
            return " ".join(tokens[2:]), " ".join(tokens[:2])
        if tokens[2].lower() in {"michel", "jean", "pierre", "marie", "paul"}:
            return tokens[3], " ".join(tokens[:3])
        return " ".join(tokens[2:]), " ".join(tokens[:2])

    # 3 composantes (ex: Sam Robin Harbor, Taylor de Sample)
    if len(tokens) == 3:
        if tokens[1].lower() in particles:
            return f"{tokens[1]} {tokens[2]}", tokens[0]
        return tokens[2], f"{tokens[0]} {tokens[1]}"

    # Plus de 4 composantes : par défaut le dernier mot est le nom
    return tokens[-1], " ".join(tokens[:-1])


def get_student_sort_key(folder_or_name: str) -> Tuple[str, str, str]:
    """
    Génère une clé de tri tuple (nom_de_famille, prenoms, da)
    assurant l'ordre alphabétique des noms de famille tel qu'affiché dans Microsoft Teams.
    """
    name, da = extract_student_identity(folder_or_name)
    last_name, first_name = split_first_last_name(name)
    return (
        normalize_for_sort(last_name),
        normalize_for_sort(first_name),
        da,
    )


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
