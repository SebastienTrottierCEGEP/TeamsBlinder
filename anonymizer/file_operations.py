"""
Module des opérations sur le système de fichiers :
- Sélection de la version la plus récente (Version N maximale) et copie vers destination
- Extraction récursive des archives .zip et suppression sécurisée
- Renommage de fichiers/dossiers contenant l'identité de l'étudiant
- Remplacement du contenu textuel (noms -> pseudonyme, DA -> XXXXXXX)
"""

import os
import re
import shutil
import zipfile
from typing import Dict, List, Optional, Set, Tuple


TEXT_EXTENSIONS = {
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
    ".cs", ".java", ".py", ".pyw", ".ipynb",
    ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".scss",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".txt", ".md", ".markdown", ".rtf",
    ".json", ".xml", ".yaml", ".yml", ".ini", ".properties", ".toml", ".csv",
    ".php", ".rb", ".go", ".rs", ".kt", ".swift", ".dart", ".r"
}


def find_latest_version_dir(exam_dir: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Parcourt le dossier d'examen de l'étudiant pour trouver le sous-dossier de version le plus élevé.
    Exemples: 'Version 1', 'Version 2' -> sélectionne 'Version 2'.
    Retourne (chemin_vers_dossier_version, numero_version).
    Si aucun dossier 'Version N' n'existe, retourne (exam_dir, None).
    """
    if not os.path.isdir(exam_dir):
        return None, None

    version_subdirs = []
    pattern = re.compile(r"^(?:version|v)\s*(\d+)$", re.IGNORECASE)

    for entry in os.scandir(exam_dir):
        if entry.is_dir():
            m = pattern.match(entry.name.strip())
            if m:
                v_num = int(m.group(1))
                version_subdirs.append((v_num, entry.path))

    if version_subdirs:
        # Trier par numéro de version décroissant pour avoir le N max
        version_subdirs.sort(key=lambda x: x[0], reverse=True)
        return version_subdirs[0][1], version_subdirs[0][0]

    return exam_dir, None


def prepare_student_submission(
    source_student_dir: str,
    exam_name: str,
    destination_student_dir: str,
) -> bool:
    """
    Copie la dernière version de la remise d'un étudiant vers le dossier de destination.
    Efface préalablement le dossier de destination s'il existait.
    Retourne True si des fichiers ont été trouvés et copiés, False sinon.
    """
    # Recherche du sous-dossier correspondant à l'examen
    exam_source_path = None
    for entry in os.scandir(source_student_dir):
        if entry.is_dir() and entry.name.strip().lower() == exam_name.strip().lower():
            exam_source_path = entry.path
            break

    if not exam_source_path:
        # Essayer avec correspondance partielle ou sans casse
        for entry in os.scandir(source_student_dir):
            if entry.is_dir() and exam_name.strip().lower() in entry.name.strip().lower():
                exam_source_path = entry.path
                break

    if not exam_source_path:
        return False

    latest_ver_path, v_num = find_latest_version_dir(exam_source_path)
    if not latest_ver_path or not os.path.exists(latest_ver_path):
        return False

    # Nettoyage / recréation du dossier destination
    if os.path.exists(destination_student_dir):
        shutil.rmtree(destination_student_dir)
    os.makedirs(destination_student_dir, exist_ok=True)

    # Copie de l'ensemble du contenu de la dernière version
    for item in os.listdir(latest_ver_path):
        src_item = os.path.join(latest_ver_path, item)
        dst_item = os.path.join(destination_student_dir, item)
        if os.path.isdir(src_item):
            shutil.copytree(src_item, dst_item)
        else:
            shutil.copy2(src_item, dst_item)

    return True


def extract_zip_archives(target_dir: str) -> int:
    """
    Extrait récursivement tous les fichiers .zip trouvés dans le répertoire cible
    et supprime l'archive .zip après extraction sécurisée.
    Retourne le nombre d'archives extraites.
    """
    extracted_count = 0
    while True:
        zips_found = []
        for root, _, files in os.walk(target_dir):
            for file in files:
                if file.lower().endswith(".zip"):
                    zips_found.append(os.path.join(root, file))

        if not zips_found:
            break

        for zip_path in zips_found:
            extract_folder = os.path.dirname(zip_path)
            try:
                if zipfile.is_zipfile(zip_path):
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        # Extraction sécurisée évitant les path traversals
                        for member in zf.infolist():
                            # Éviter chemins absolus ou relatifs vers le haut
                            target_path = os.path.abspath(os.path.join(extract_folder, member.filename))
                            if not target_path.startswith(os.path.abspath(extract_folder)):
                                continue
                            zf.extract(member, extract_folder)
                    os.remove(zip_path)
                    extracted_count += 1
                else:
                    # Fichier corrompu ou non zip
                    pass
            except Exception as e:
                print(f"⚠ Erreur lors de l'extraction de {zip_path}: {e}")
                # Enlever pour éviter une boucle infinie
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

    return extracted_count


def strip_accents(text: str) -> str:
    """Supprime les accents d'une chaîne de caractères."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def get_typo_variants(word: str) -> List[str]:
    """Génère les variantes par inversion de deux lettres adjacentes (ex: Gaetan -> Gatean)."""
    variants = []
    for i in range(len(word) - 1):
        swapped = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        if swapped != word:
            variants.append(swapped)
    return variants


def generate_name_patterns(student_name: str) -> List[re.Pattern]:
    """
    Génère un ensemble d'expressions régulières pour capturer les variantes
    courantes du nom d'un étudiant (Nom Prenom, Prenom Nom, sans accents, compacté, avec underscore, fautes de frappe).
    """
    patterns = []
    if not student_name:
        return patterns

    base_names = {student_name, strip_accents(student_name)}
    all_parts = set()

    for bname in base_names:
        parts = [p.strip() for p in re.split(r"[,\s_-]+", bname) if p.strip()]
        if not parts:
            continue

        for p in parts:
            all_parts.add(p)
            for v in get_typo_variants(p):
                all_parts.add(v)

        full_escaped = re.escape(bname)
        patterns.append(re.compile(rf"\b{full_escaped}\b", re.IGNORECASE))

        if len(parts) >= 2:
            p1_variants = [parts[0]] + get_typo_variants(parts[0])
            p2_variants = [parts[1]] + get_typo_variants(parts[1])

            for p1 in p1_variants:
                for p2 in p2_variants:
                    p1_esc = re.escape(p1)
                    p2_esc = re.escape(p2)
                    # "Nom Prenom" ou "Prenom Nom"
                    patterns.append(re.compile(rf"\b{p1_esc}\s+{p2_esc}\b", re.IGNORECASE))
                    patterns.append(re.compile(rf"\b{p2_esc}\s+{p1_esc}\b", re.IGNORECASE))
                    # "Nom_Prenom" ou "Prenom_Nom"
                    patterns.append(re.compile(rf"{p1_esc}[_.-]+{p2_esc}", re.IGNORECASE))
                    patterns.append(re.compile(rf"{p2_esc}[_.-]+{p1_esc}", re.IGNORECASE))
                    # "NomPrenom" ou "PrenomNom" (ex: SimardGaetan ou GateanSimard)
                    patterns.append(re.compile(rf"{p1_esc}{p2_esc}", re.IGNORECASE))
                    patterns.append(re.compile(rf"{p2_esc}{p1_esc}", re.IGNORECASE))

    # Parties individuelles du nom (si au moins 4 caractères)
    for p in all_parts:
        if len(p) >= 4:
            p_esc = re.escape(p)
            patterns.append(re.compile(rf"\b{p_esc}\b", re.IGNORECASE))

    return patterns


def anonymize_text_content(
    text: str,
    alias: str,
    name_patterns: List[re.Pattern],
    da: str = "",
) -> Tuple[str, int]:
    """
    Remplace les occurrences des variantes du nom par l'alias et les DA 7 chiffres par XXXXXXX.
    Retourne (texte_modifié, nombre_de_remplacements).
    """
    modified = text
    count = 0

    # 1. Remplacement des variantes de nom
    for pat in name_patterns:
        modified, n = pat.subn(alias, modified)
        count += n

    # 2. Remplacement du DA exact (si fourni)
    if da and len(da) == 7:
        da_pat = re.compile(rf"\b{re.escape(da)}\b")
        modified, n = da_pat.subn("XXXXXXX", modified)
        count += n

    # 3. Remplacement systématique de tout DA étudiant (7 chiffres consécutifs)
    general_da_pat = re.compile(r"\b\d{7}\b")
    modified, n = general_da_pat.subn("XXXXXXX", modified)
    count += n

    return modified, count


def anonymize_docx_file(
    docx_path: str,
    alias: str,
    name_patterns: List[re.Pattern],
    da: str = "",
) -> int:
    """
    Anonymise un document Word (.docx) en modifiant son fichier XML interne word/document.xml.
    """
    temp_dir = docx_path + "_unpacked_tmp"
    replacements = 0
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            zf.extractall(temp_dir)

        doc_xml_path = os.path.join(temp_dir, "word", "document.xml")
        if os.path.exists(doc_xml_path):
            with open(doc_xml_path, "r", encoding="utf-8") as f:
                content = f.read()

            new_content, count = anonymize_text_content(content, alias, name_patterns, da)
            replacements += count

            if count > 0:
                with open(doc_xml_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                # Recompresser le document docx
                os.remove(docx_path)
                with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            full_p = os.path.join(root, file)
                            rel_p = os.path.relpath(full_p, temp_dir)
                            zf.write(full_p, rel_p)
    except Exception as e:
        print(f"⚠ Erreur lors du traitement du document Word {docx_path}: {e}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    return replacements


def anonymize_filenames_and_contents(
    student_dir: str,
    student_name: str,
    da: str,
    alias: str,
    additional_variations: Optional[List[str]] = None,
) -> Dict[str, int]:
    """
    Parcourt l'ensemble des fichiers du dossier étudiant anonymisé :
    - Renomme les fichiers/dossiers contenant le nom ou le DA de l'étudiant
    - Modifie le contenu textuel ou docx pour remplacer les noms et DAs.
    Retourne des statistiques {'files_renamed': X, 'files_modified': Y}.
    """
    stats = {"files_renamed": 0, "files_modified": 0}
    name_patterns = generate_name_patterns(student_name)

    # Ajouter d'éventuelles variantes supplémentaires (fournies par l'agent ou détectées)
    if additional_variations:
        for var in additional_variations:
            if var and len(var) >= 3:
                name_patterns.append(re.compile(re.escape(var), re.IGNORECASE))

    # Étape 1 : Modification des contenus des fichiers
    for root, _, files in os.walk(student_dir):
        for file in files:
            file_path = os.path.join(root, file)
            _, ext = os.path.splitext(file.lower())

            if ext == ".docx":
                n_rep = anonymize_docx_file(file_path, alias, name_patterns, da)
                if n_rep > 0:
                    stats["files_modified"] += 1
            elif ext in TEXT_EXTENSIONS or ext == "":
                # Tentative de lecture en texte avec fallback encodings
                for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                    try:
                        with open(file_path, "r", encoding=encoding) as f:
                            text = f.read()
                        new_text, n_rep = anonymize_text_content(text, alias, name_patterns, da)
                        if n_rep > 0:
                            with open(file_path, "w", encoding=encoding) as f:
                                f.write(new_text)
                            stats["files_modified"] += 1
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                    except Exception:
                        break

    # Étape 2 : Renommage des fichiers et dossiers (du plus profond au plus superficiel)
    for root, dirs, files in os.walk(student_dir, topdown=False):
        for item in files + dirs:
            old_path = os.path.join(root, item)
            new_item = item

            # Remplacement des variantes de nom
            for pat in name_patterns:
                new_item = pat.sub(alias, new_item)

            # Remplacement du DA
            if da and len(da) == 7:
                new_item = new_item.replace(da, "XXXXXXX")
            new_item = re.sub(r"\b\d{7}\b", "XXXXXXX", new_item)

            if new_item != item:
                new_path = os.path.join(root, new_item)
                try:
                    if not os.path.exists(new_path):
                        os.rename(old_path, new_path)
                        stats["files_renamed"] += 1
                except Exception as e:
                    print(f"⚠ Impossible de renommer {old_path} vers {new_path}: {e}")

    return stats
