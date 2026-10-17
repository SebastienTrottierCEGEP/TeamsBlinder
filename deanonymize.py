#!/usr/bin/env python3
"""
TeamsBlinder - Module et outil de dé-anonymisation.
Accepte un fichier en entrée et génère <nom_de_fichier>_out.<ext> en remplaçant :
- Les alias étudiants (ex: etudiantXX) par leurs vrais noms
- Les numéros masqués (XXXXXXX) par les vrais codes DA (7 chiffres)
suivant la table de correspondance de mapping_central.csv.
"""

import argparse
import csv
import os
import re
import shutil
import sys
import zipfile
from typing import Dict, List, Optional, Set, Tuple


def find_mapping_file(custom_path: Optional[str] = None) -> str:
    """Localise le fichier mapping_central.csv."""
    if custom_path and os.path.isfile(custom_path):
        return os.path.abspath(custom_path)

    # 1. Vérification dans config.properties
    config_file = "config.properties"
    if os.path.isfile(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("mapping_file="):
                        cfg_path = line.split("=", 1)[1].strip()
                        if os.path.isfile(cfg_path):
                            return os.path.abspath(cfg_path)
        except Exception:
            pass

    # 2. Chemins par défaut courants
    candidates = [
        "mapping_central.csv",
        "./mapping_central.csv",
        "SampleDir_Anonymise/mapping_central.csv",
        "./SampleDir_Anonymise/mapping_central.csv",
        "../mapping_central.csv",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    raise FileNotFoundError(
        "Fichier mapping_central.csv introuvable. "
        "Spécifiez son emplacement avec l'option --mapping <chemin>."
    )


def load_mappings(mapping_file: str) -> Dict[str, Dict[str, str]]:
    """
    Charge les correspondances depuis mapping_central.csv.
    Retourne un dictionnaire {alias_lower: {alias, name, da, ...}}.
    """
    mappings: Dict[str, Dict[str, str]] = {}
    with open(mapping_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            alias = (row.get("alias") or "").strip()
            student_name = (row.get("student_name") or "").strip()
            da = (row.get("da") or "").strip()
            if alias and (student_name or da):
                mappings[alias.lower()] = {
                    "alias": alias,
                    "student_name": student_name,
                    "da": da,
                    "exam_name": (row.get("exam_name") or "").strip(),
                }
    return mappings


def get_output_filepath(input_path: str, custom_output: Optional[str] = None) -> str:
    """Calcule le chemin de sortie : <nom de fichier>_out.<ext>."""
    if custom_output:
        return os.path.abspath(custom_output)

    abs_in = os.path.abspath(input_path)
    dirname, basename = os.path.split(abs_in)
    root, ext = os.path.splitext(basename)
    out_basename = f"{root}_out{ext}"
    return os.path.join(dirname, out_basename)


def deanonymize_text(
    text: str,
    mappings: Dict[str, Dict[str, str]],
    append_da_to_name: bool = False,
) -> Tuple[str, Dict[str, int]]:
    """
    Remplace les alias et XXXXXXX dans le contenu textuel :
    - etudiantXX -> student_name (ou student_name (da) si append_da_to_name=True)
    - XXXXXXX -> da correspondant (sur la même ligne ou sur des lignes adjacentes/proches)
    """
    stats = {"aliases_replaced": 0, "das_replaced": 0}
    if not text:
        return text, stats

    # Trier les alias par longueur décroissante (ex: etudiant10 avant etudiant1)
    sorted_aliases = sorted(mappings.keys(), key=len, reverse=True)

    lines = text.splitlines(keepends=True)

    # 1. Cartographier les alias présents sur chaque ligne
    line_aliases = {}
    all_present_aliases = set()
    for idx, line in enumerate(lines):
        for alias_low in sorted_aliases:
            if re.search(rf"\b{re.escape(alias_low)}\b", line, re.IGNORECASE):
                line_aliases[idx] = alias_low
                all_present_aliases.add(alias_low)
                break

    single_alias = list(all_present_aliases)[0] if len(all_present_aliases) == 1 else None

    # 2. Résoudre le DA pour chaque ligne contenant XXXXXXX par analyse de proximité
    da_resolution = {}
    max_d = len(lines)
    for idx, line in enumerate(lines):
        if "XXXXXXX" in line:
            # Cas 1 : Même ligne
            if idx in line_aliases:
                da_resolution[idx] = line_aliases[idx]
                continue
            # Cas 2 : Fichier à étudiant unique
            if single_alias:
                da_resolution[idx] = single_alias
                continue
            # Cas 3 : Recherche de proximité bidirectionnelle (ligne précédente ou suivante la plus proche)
            best_alias = None
            for d in range(1, max_d):
                if idx - d in line_aliases:
                    best_alias = line_aliases[idx - d]
                    break
                if idx + d in line_aliases:
                    best_alias = line_aliases[idx + d]
                    break
            if best_alias:
                da_resolution[idx] = best_alias

    # 3. Effectuer les remplacements
    out_lines = []
    for idx, line in enumerate(lines):
        # Remplacement du DA
        if idx in da_resolution:
            alias_match = da_resolution[idx]
            da_val = mappings[alias_match]["da"]
            if da_val:
                line, count_da = re.subn(r"\bXXXXXXX\b", da_val, line)
                stats["das_replaced"] += count_da

        # Remplacement des alias étudiants
        for alias_low in sorted_aliases:
            pattern = re.compile(rf"\b{re.escape(alias_low)}\b", re.IGNORECASE)
            info = mappings[alias_low]
            rep = info["student_name"]
            if append_da_to_name and info["da"]:
                rep = f"{rep} ({info['da']})"

            line, count_alias = pattern.subn(rep, line)
            stats["aliases_replaced"] += count_alias

        out_lines.append(line)

    result_text = "".join(out_lines)

    # 4. Sécurité pour tout XXXXXXX restant si le fichier n'appartient qu'à un seul étudiant
    if single_alias and "XXXXXXX" in result_text:
        da_val = mappings[single_alias]["da"]
        if da_val:
            result_text, extra_das = re.subn(r"\bXXXXXXX\b", da_val, result_text)
            stats["das_replaced"] += extra_das

    return result_text, stats


def deanonymize_docx(
    docx_path: str,
    output_path: str,
    mappings: Dict[str, Dict[str, str]],
    append_da_to_name: bool = False,
) -> Dict[str, int]:
    """Dé-anonymise un document Word (.docx)."""
    temp_dir = docx_path + "_unpacked_tmp"
    stats = {"aliases_replaced": 0, "das_replaced": 0}
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            zf.extractall(temp_dir)

        doc_xml_path = os.path.join(temp_dir, "word", "document.xml")
        if os.path.exists(doc_xml_path):
            with open(doc_xml_path, "r", encoding="utf-8") as f:
                content = f.read()

            new_content, stats = deanonymize_text(content, mappings, append_da_to_name)
            with open(doc_xml_path, "w", encoding="utf-8") as f:
                f.write(new_content)

        if os.path.exists(output_path):
            os.remove(output_path)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, temp_dir)
                    zf.write(full_p, rel_p)
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    return stats


def process_file(
    input_file: str,
    output_file: Optional[str] = None,
    mapping_file: Optional[str] = None,
    append_da: bool = False,
) -> Tuple[str, Dict[str, int]]:
    """Traite le fichier d'entrée et écrit le fichier de sortie dé-anonymisé."""
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Le fichier source '{input_file}' n'existe pas.")

    actual_mapping_path = find_mapping_file(mapping_file)
    mappings = load_mappings(actual_mapping_path)
    if not mappings:
        raise ValueError(f"Aucune correspondance trouvée dans {actual_mapping_path}.")

    out_path = get_output_filepath(input_file, output_file)

    _, ext = os.path.splitext(input_file.lower())
    if ext == ".docx":
        stats = deanonymize_docx(input_file, out_path, mappings, append_da_to_name=append_da)
    else:
        # Fichiers texte, code, csv, markdown, yaml, json, etc.
        content = None
        used_encoding = "utf-8"
        for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            try:
                with open(input_file, "r", encoding=enc) as f:
                    content = f.read()
                used_encoding = enc
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            raise ValueError(f"Impossible de lire le fichier '{input_file}' avec les encodages usuels.")

        new_content, stats = deanonymize_text(content, mappings, append_da_to_name=append_da)

        with open(out_path, "w", encoding=used_encoding) as f:
            f.write(new_content)

    return out_path, stats


def main():
    parser = argparse.ArgumentParser(
        description="TeamsBlinder - Dé-anonymise un fichier en remplaçant etudiantXX par les vrais noms et XXXXXXX par les DA réels."
    )
    parser.add_argument("file", help="Chemin du fichier à dé-anonymiser")
    parser.add_argument("-o", "--output", help="Chemin du fichier de sortie (par défaut: <nom>_out.<ext>)")
    parser.add_argument("-m", "--mapping", help="Chemin vers mapping_central.csv (détecté automatiquement par défaut)")
    parser.add_argument(
        "--append-da",
        action="store_true",
        help="Ajoute le DA entre parenthèses après le nom (ex: Nom Étudiant (1234567)) même sans XXXXXXX",
    )

    args = parser.parse_args()

    try:
        out_path, stats = process_file(
            input_file=args.file,
            output_file=args.output,
            mapping_file=args.mapping,
            append_da=args.append_da,
        )
        print("=" * 60)
        print("        TEAMSBLINDER - DÉ-ANONYMISATION DE FICHIER          ")
        print("=" * 60)
        print(f"[*] Fichier source  : {args.file}")
        print(f"[*] Fichier généré  : {out_path}")
        print(f"[*] Alias remplacés : {stats['aliases_replaced']}")
        print(f"[*] DA restaurés    : {stats['das_replaced']}")
        print("=" * 60)
        print("✔ Dé-anonymisation terminée avec succès !")
    except Exception as e:
        print(f"❌ Erreur : {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
