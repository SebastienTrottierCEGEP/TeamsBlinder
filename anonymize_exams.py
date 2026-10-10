#!/usr/bin/env python3
"""
TeamsBlinder - Script principal d'anonymisation d'examens étudiants.

Lit les propriétés depuis config.properties, parcourt les dossiers étudiants,
attribue les pseudonymes, copie la dernière version soumise, extrait les archives .zip,
et anonymise les noms de fichiers et contenus textuels via Regex et le Strands Agent Harness.
"""

import os
import sys
import time

# Configuration sécurisée de l'encodage de la console (Windows cp1252 / Linux UTF-8)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from anonymizer.config import load_config
from anonymizer.identity import extract_student_identity, MappingTracker
from anonymizer.file_operations import (
    prepare_student_submission,
    extract_zip_archives,
    scan_submission_manifest,
    anonymize_filenames_and_contents,
)
from anonymizer.agent_harness import AnonymizationAgentHarness


def main():
    print("=" * 65)
    print("      TEAMSBLINDER - ANONYMISATION DES EXAMENS ETUDIANTS        ")
    print("=" * 65)

    # 1. Chargement de la configuration
    config = load_config("config.properties")
    src_base = config.get("submissions_base_path", "./SampleDir")
    exam_name = config.get("exam_name", "Objets Connectes 1 - Examen 1")
    dst_base = config.get("anonymized_base_path", "./SampleDir_Anonymise")
    prefix = config.get("replacement_prefix", "etudiant")
    mapping_file = config.get("mapping_file", os.path.join(dst_base, "mapping_central.csv"))
    model_id = config.get("model_id", "llama3.2:3b")
    host = config.get("host", "http://localhost:11434")

    print(f"[*] Dossier source        : {src_base}")
    print(f"[*] Examen cible          : {exam_name}")
    print(f"[*] Dossier destination   : {dst_base}")
    print(f"[*] Prefix de substitution: {prefix}")
    print(f"[*] Fichier de mapping    : {mapping_file}")
    print(f"[*] Modele Ollama (Agent) : {model_id} ({host})")
    print("-" * 65)

    if not os.path.isdir(src_base):
        print(f"[!] Erreur : Le dossier source '{src_base}' n'existe pas.")
        sys.exit(1)

    os.makedirs(dst_base, exist_ok=True)

    # 2. Initialisation du gestionnaire de mapping et de l'agent harness
    tracker = MappingTracker(mapping_file, prefix=prefix)
    agent_harness = AnonymizationAgentHarness(host=host, model_id=model_id)

    # 3. Découverte des répertoires étudiants
    student_dirs = []
    for entry in sorted(os.scandir(src_base), key=lambda e: e.name.lower()):
        if entry.is_dir() and not entry.name.startswith("."):
            student_dirs.append(entry)

    if not student_dirs:
        print(f"[!] Aucun repertoire etudiant trouve dans '{src_base}'.")
        sys.exit(0)

    print(f"[+] {len(student_dirs)} repertoire(s) etudiant(s) detecte(s).\n")

    # 4. Traitement étudiant par étudiant
    total_processed = 0
    total_skipped = 0
    total_renamed = 0
    total_modified = 0
    start_time = time.time()

    for idx, s_entry in enumerate(student_dirs, start=1):
        s_folder_name = s_entry.name
        student_name, da = extract_student_identity(s_folder_name)

        # Attribution de l'alias unique
        alias = tracker.get_or_create_alias(
            student_name=student_name,
            da=da,
            source_folder=s_entry.path,
            destination_folder=os.path.join(dst_base, prefix),
            exam_name=exam_name,
        )

        dst_student_dir = os.path.join(dst_base, alias)

        print(f"[{idx}/{len(student_dirs)}] {s_folder_name} -> {alias}")
        print(f"   * Identite : Nom='{student_name}' | DA={da if da else 'Non detecte'}")

        # Étape A : Copie de la dernière version (Version N)
        copied = prepare_student_submission(
            source_student_dir=s_entry.path,
            exam_name=exam_name,
            destination_student_dir=dst_student_dir,
        )

        if not copied:
            print(f"   [!] Pas de remise trouvee pour l'examen '{exam_name}'. Ignore.\n")
            total_skipped += 1
            continue

        # Étape B : Décompression des archives .zip
        nb_zips = extract_zip_archives(dst_student_dir)
        if nb_zips > 0:
            print(f"   [+] {nb_zips} archive(s) .zip extraite(s) et nettoyee(s).")

        # Étape C : Scan du manifeste et analyse par l'Agent Strands
        filenames, snippets = scan_submission_manifest(dst_student_dir, student_name, da)
        print(f"   [+] Manifeste extrait : {len(filenames)} fichier(s)/dossier(s), {len(snippets)} extrait(s) pertinent(s).")
        print("   [+] Analyse par l'Agent Strands (recherche de variantes, identifiants et entites)...")
        agent_aliases = agent_harness.discover_aliases(
            student_name=student_name,
            da=da,
            alias=alias,
            filenames=filenames,
            snippets=snippets,
        )
        if agent_aliases:
            print(f"       > Alias detectes par l'Agent : {agent_aliases}")

        # Étape D : Passe chirurgicale (permutations combinatoires + decouvertes Agent)
        stats = anonymize_filenames_and_contents(
            student_dir=dst_student_dir,
            student_name=student_name,
            da=da,
            alias=alias,
            extra_aliases=agent_aliases,
        )

        total_renamed += stats["files_renamed"]
        total_modified += stats["files_modified"]
        total_processed += 1

        print(f"   [+] Anonymisation terminee ({stats['files_renamed']} fichier(s) renomme(s), {stats['files_modified']} fichier(s) modifie(s)).\n")

    elapsed = time.time() - start_time

    # 5. Rapport final
    print("=" * 65)
    print("                   RAPPORT D'ANONYMISATION                     ")
    print("=" * 65)
    print(f"[+] Etudiants traites avec succes : {total_processed}/{len(student_dirs)}")
    if total_skipped > 0:
        print(f"[!] Etudiants sans remise pour '{exam_name}' : {total_skipped}")
    print(f"[+] Fichiers au contenu anonymise : {total_modified}")
    print(f"[+] Fichiers/dossiers renommes    : {total_renamed}")
    print(f"[*] Fichier central de mapping    : {mapping_file}")
    print(f"[*] Temps total d'execution       : {elapsed:.2f}s")
    print("=" * 65)
    print("[+] Operation d'anonymisation terminee avec succes !\n")


if __name__ == "__main__":
    main()
