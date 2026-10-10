"""
Module des opérations sur le système de fichiers pour TeamsBlinder :
- Sélection de la version la plus récente (Version N maximale) et copie vers destination
- Extraction récursive des archives .zip et suppression sécurisée
- Scan complet du manifeste (fichiers et extraits de code) pour l'agent IA
- Génération combinatoire exhaustive d'alias (noms composés, multiples prénoms, initiales)
- Renommage de fichiers/dossiers contenant l'identité de l'étudiant
- Remplacement du contenu textuel (noms -> pseudonyme, DA -> XXXXXXX)
"""

import itertools
import os
import re
import shutil
import unicodedata
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


GENERIC_PROTECTED_TERMS = {
    "automation", "automations", "configuration", "script", "scripts",
    "known_devices", "device_tracker", "person", "notify", "sensor",
    "input_number", "input_boolean", "input_text", "input_select",
    "zone", "zones", "lovelace", "markdown", "temperature", "examen",
    "exam", "tableau", "bord", "tableaudebord", "copie", "capture",
    "ecran", "texte", "submission", "nomzone", "efforts", "resultats",
    "effort", "resultat", "olaf", "gabriel", "elodie", "eve", "luneblue",
    "file", "local", "da", "nomprenom", "username", "etudiant", "student"
}


def strip_accents(text: str) -> str:
    """Supprime les accents d'une chaîne de caractères."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def cleanup_metadata_files(target_dir: str) -> None:
    """Supprime récursivement les fichiers de métadonnées résiduels (ex: Zone.Identifier)."""
    for root, _, files in os.walk(target_dir, topdown=False):
        for f in files:
            if "Zone.Identifier" in f or ":" in f:
                try:
                    os.remove(os.path.join(root, f))
                except Exception:
                    pass


def levenshtein_dist(s1: str, s2: str) -> int:
    """Distance de Levenshtein entre deux chaînes."""
    s1, s2 = s1.lower(), s2.lower()
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev[j + 1] + 1
            deletions = curr[j] + 1
            substitutions = prev[j] + (c1 != c2)
            curr.append(min(insertions, deletions, substitutions))
        prev = curr
    return prev[-1]


def split_filename_tokens(filename: str) -> List[str]:
    """Découpe un nom de fichier par ponctuation et CamelCase."""
    tokens = []
    chunks = re.split(r'[^A-Za-z0-9\u00C0-\u00FF]+', filename)
    for chunk in chunks:
        sub = re.findall(r'[A-Z\u00C0-\u00DD][a-z\u00E0-\u00FF]+|[a-z\u00E0-\u00FF]+|[A-Z\u00C0-\u00DD]+', chunk)
        tokens.extend(sub if sub else [chunk])
    return [t for t in tokens if len(t) >= 2]


def get_name_tokens(student_name: str) -> List[str]:
    """Extrait toutes les composantes simples et composées du nom."""
    clean = student_name.strip()
    raw_tokens = []

    for part in clean.split():
        part = part.strip(",()_")
        if part:
            raw_tokens.append(part)
            if "-" in part:
                subparts = part.split("-")
                raw_tokens.extend([sp for sp in subparts if len(sp) >= 2])
                raw_tokens.append("".join(subparts))  # ex: GeraldMansfield

    seen = set()
    result = []
    for t in raw_tokens:
        t_clean = strip_accents(t)
        if t_clean.lower() not in seen and len(t_clean) >= 2:
            seen.add(t_clean.lower())
            result.append(t)
    return result


def generate_all_student_aliases(
    student_name: str,
    extra_tokens: Optional[List[str]] = None,
) -> List[str]:
    """
    Génère exhaustivement toutes les variantes d'alias possibles pour un étudiant :
    - Noms composés avec et sans tiret (ex: Gerald-Mansfield, GeraldMansfield)
    - Inversions complètes de 2 et 3 composantes (ex: BernouilliAmadi, CharlesMandla, CharlesMandlaEric)
    - Séparateurs variés : collé, espace, tiret, underscore, point, minuscules
    - Déclinaisons avec initiales (ex: mathieu_r_g)
    Trie par longueur décroissante pour garantir des remplacements parfaits.
    """
    tokens = get_name_tokens(student_name)
    if extra_tokens:
        existing_low = {t.lower() for t in tokens}
        for et in extra_tokens:
            if et and len(et) >= 3 and et.lower() not in existing_low:
                tokens.append(et)
                existing_low.add(et.lower())

    aliases = set()

    # 1. Nom complet original et sans accents
    aliases.add(student_name)
    aliases.add(strip_accents(student_name))

    # 2. Chaque token individuel de longueur >= 3
    for t in tokens:
        if len(t) >= 3:
            aliases.add(t)
            aliases.add(strip_accents(t))

    # 3. Toutes les permutations de 2 et 3 tokens
    max_r = min(len(tokens) + 1, 4)
    for r in range(2, max_r):
        for combo in itertools.permutations(tokens, r):
            c_raw = list(combo)
            c_clean = [strip_accents(x) for x in c_raw]

            for c in [c_raw, c_clean]:
                aliases.add("".join(c))                     # BernouilliAmadi, CharlesMandlaEric
                aliases.add(" ".join(c))                     # Bernouilli Amadi
                aliases.add("-".join(c))                     # Bernouilli-Amadi
                aliases.add("_".join(c))                     # bernouilli_amadi
                aliases.add(".".join(c))                     # bernouilli.amadi
                aliases.add("_".join(x.lower() for x in c))  # amadi_bernouilli
                aliases.add("".join(x.lower() for x in c))   # amadibernouilli

    # 4. Variantes avec initiales (ex: mathieu_r_g, mathieu_roberge_girardeau)
    first_names = [t for t in tokens if "-" not in t]
    compound_names = [t for t in tokens if "-" in t]
    if compound_names and first_names:
        for fn in first_names:
            for cn in compound_names:
                cn_parts = cn.split("-")
                initials = "_".join(p[0].lower() for p in cn_parts)
                aliases.add(f"{fn.lower()}_{initials}")       # mathieu_r_g
                aliases.add(f"{fn.lower()}_{''.join(p[0].lower() for p in cn_parts)}")  # mathieu_rg

    # Filtrer les alias trop courts et termes génériques, trier par longueur décroissante
    cleaned_aliases = [
        a.strip() for a in aliases
        if len(a.strip()) >= 3 and a.strip().lower() not in GENERIC_PROTECTED_TERMS
    ]
    cleaned_aliases.sort(key=len, reverse=True)
    return cleaned_aliases


# Alias de compatibilité ascendante
generate_name_patterns = generate_all_student_aliases


def find_latest_version_dir(exam_dir: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Parcourt le dossier d'examen de l'étudiant pour trouver le sous-dossier de version le plus élevé.
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
    """
    exam_source_path = None
    for entry in os.scandir(source_student_dir):
        if entry.is_dir() and entry.name.strip().lower() == exam_name.strip().lower():
            exam_source_path = entry.path
            break

    if not exam_source_path:
        for entry in os.scandir(source_student_dir):
            if entry.is_dir() and exam_name.strip().lower() in entry.name.strip().lower():
                exam_source_path = entry.path
                break

    if not exam_source_path:
        return False

    latest_ver_path, _ = find_latest_version_dir(exam_source_path)
    if not latest_ver_path or not os.path.exists(latest_ver_path):
        return False

    if os.path.exists(destination_student_dir):
        shutil.rmtree(destination_student_dir)
    os.makedirs(destination_student_dir, exist_ok=True)

    for item in os.listdir(latest_ver_path):
        src_item = os.path.join(latest_ver_path, item)
        dst_item = os.path.join(destination_student_dir, item)
        if os.path.isdir(src_item):
            shutil.copytree(src_item, dst_item)
        else:
            shutil.copy2(src_item, dst_item)

    cleanup_metadata_files(destination_student_dir)
    return True


def extract_zip_archives(target_dir: str) -> int:
    """
    Extrait récursivement tous les fichiers .zip et supprime l'archive .zip après extraction.
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
                        for member in zf.infolist():
                            target_path = os.path.abspath(os.path.join(extract_folder, member.filename))
                            if not target_path.startswith(os.path.abspath(extract_folder)):
                                continue
                            zf.extract(member, extract_folder)
                    os.remove(zip_path)
                    extracted_count += 1
            except Exception as e:
                print(f"⚠ Erreur extraction {zip_path}: {e}")
                try:
                    os.remove(zip_path)
                except Exception:
                    pass

    cleanup_metadata_files(target_dir)
    return extracted_count


def scan_submission_manifest(
    student_dir: str,
    student_name: str,
    da: str,
) -> Tuple[List[str], List[str]]:
    """
    Scanne l'ensemble des noms de fichiers et le contenu des fichiers texte
    pour collecter un manifeste complet à fournir à l'agent Strands.
    Retourne (liste_fichiers, liste_extraits_lignes_pertinentes).
    """
    tokens = get_name_tokens(student_name)
    tokens_lower = [t.lower() for t in tokens if len(t) >= 3]
    if da:
        tokens_lower.append(da)

    filenames = []
    snippets = []
    seen_snippets = set()

    # Mots clés typiques d'identifiants
    keyword_patterns = [
        re.compile(r"notify\.[a-z0-9_]+", re.IGNORECASE),
        re.compile(r"person\.[a-z0-9_]+", re.IGNORECASE),
        re.compile(r"device_tracker\.[a-z0-9_]+", re.IGNORECASE),
        re.compile(r"name:\s*[\"'].*?[\"']", re.IGNORECASE),
        re.compile(r"value:\s*[\"'].*?[\"']", re.IGNORECASE),
        re.compile(r"author\s*:\s*.*", re.IGNORECASE),
    ]

    for root, dirs, files in os.walk(student_dir):
        for d in dirs:
            rel_d = os.path.relpath(os.path.join(root, d), student_dir)
            filenames.append(rel_d + "/")

        for f in files:
            if ":" in f or "Zone.Identifier" in f:
                continue
            file_path = os.path.join(root, f)
            rel_p = os.path.relpath(file_path, student_dir)
            filenames.append(rel_p)

            _, ext = os.path.splitext(f.lower())
            if ext in TEXT_EXTENSIONS or ext == "":
                for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                    try:
                        with open(file_path, "r", encoding=encoding, errors="ignore") as fh:
                            lines = fh.readlines()
                        for line in lines[:300]:  # Limiter à 300 lignes par fichier
                            line_str = line.strip()
                            if not line_str:
                                continue
                            line_lower = line_str.lower()

                            # Match si contient un jeton de nom ou un DA
                            has_token = any(t in line_lower for t in tokens_lower)
                            has_keyword = any(pat.search(line_str) for pat in keyword_patterns)

                            if has_token or has_keyword:
                                snippet_entry = f"{rel_p}: {line_str[:120]}"
                                if snippet_entry not in seen_snippets:
                                    seen_snippets.add(snippet_entry)
                                    snippets.append(snippet_entry)
                        break
                    except Exception:
                        continue

    return filenames, snippets[:60]  # Limite de 60 snippets pour le contexte LLM


def anonymize_text_content(
    text: str,
    alias: str,
    aliases_to_replace: List[str],
    da: str = "",
) -> Tuple[str, int]:
    """
    Remplace les occurrences des alias par l'alias cible et tout DA à 7 chiffres par XXXXXXX.
    Traite dans l'ordre de longueur décroissante pour éviter le fractionnement des noms composés.
    """
    modified = text
    count = 0

    # 1. Remplacement des alias (triés du plus long au plus court)
    for target in aliases_to_replace:
        if not target:
            continue
        if isinstance(target, re.Pattern):
            modified, n = target.subn(alias, modified)
            count += n
            continue
        if len(target) < 3 or target == alias:
            continue
        pattern = re.compile(re.escape(target), re.IGNORECASE)
        modified, n = pattern.subn(alias, modified)
        count += n

    # 2. Remplacement du DA spécifique
    if da and len(da) == 7:
        da_pat = re.compile(rf"\b{re.escape(da)}\b")
        modified, n = da_pat.subn("XXXXXXX", modified)
        count += n

    # 3. Remplacement systématique de tout numéro de DA (7 chiffres consécutifs)
    general_da_pat = re.compile(r"\b\d{7}\b")
    modified, n = general_da_pat.subn("XXXXXXX", modified)
    count += n

    return modified, count


def anonymize_docx_file(
    docx_path: str,
    alias: str,
    aliases_to_replace: List[str],
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

            new_content, count = anonymize_text_content(content, alias, aliases_to_replace, da)
            replacements += count

            if count > 0:
                with open(doc_xml_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                os.remove(docx_path)
                with zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(temp_dir):
                        for file in files:
                            full_p = os.path.join(root, file)
                            rel_p = os.path.relpath(full_p, temp_dir)
                            zf.write(full_p, rel_p)
    except Exception as e:
        print(f"⚠ Erreur traitement document Word {docx_path}: {e}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    return replacements


def anonymize_filenames_and_contents(
    student_dir: str,
    student_name: str,
    da: str,
    alias: str,
    extra_aliases: Optional[List[str]] = None,
) -> Dict[str, int]:
    """
    Parcourt l'ensemble des fichiers du dossier étudiant :
    - Détecte d'éventuelles fautes de frappe dans les noms de fichiers (ex: Gatean pour Gaetan)
    - Compile tous les alias (combinatoires + extraits par l'agent IA)
    - Filtre strictement pour exclure les noms génériques Home Assistant / examens
    - Trie par longueur décroissante
    - Modifie le contenu textuel / code / docx
    - Renomme tous les fichiers et dossiers (du plus profond au plus superficiel) avec gestion des collisions.
    """
    stats = {"files_renamed": 0, "files_modified": 0}

    # Nettoyage initial des métadonnées Zone.Identifier
    cleanup_metadata_files(student_dir)

    # 1. Détection automatique des fautes de frappe dans les fichiers (ex: Gatean vs Gaetan)
    base_tokens = get_name_tokens(student_name)
    detected_typos = []
    for root, _, files in os.walk(student_dir):
        for f in files:
            for piece in split_filename_tokens(f):
                for bt in base_tokens:
                    if len(bt) >= 4 and abs(len(piece) - len(bt)) <= 1:
                        is_anagram = sorted(piece.lower()) == sorted(bt.lower())
                        dist = levenshtein_dist(piece, bt)
                        if (is_anagram or dist <= 2) and piece.lower() != bt.lower():
                            if piece.lower() not in GENERIC_PROTECTED_TERMS:
                                detected_typos.append(piece)

    all_aliases_set = set(generate_all_student_aliases(student_name, extra_tokens=detected_typos))

    # 2. Filtrage des alias supplémentaires découverts par l'Agent IA
    if extra_aliases:
        cand_tokens = [t.lower() for t in base_tokens]
        if da:
            cand_tokens.append(da)
        for ea in extra_aliases:
            ea_clean = ea.strip("\"' \t\r\n")
            if not ea_clean or len(ea_clean) < 3 or ea_clean == alias:
                continue
            if ea_clean.lower() in GENERIC_PROTECTED_TERMS:
                continue
            base_cand = os.path.basename(ea_clean).lower()
            if base_cand.endswith((".yaml", ".yml", ".txt", ".png", ".jpg", ".zip", ".docx")):
                base_cand = os.path.splitext(base_cand)[0]
            if base_cand in GENERIC_PROTECTED_TERMS:
                continue
            # Doit être relié à l'identité de l'étudiant
            has_student_token = any(tok in ea_clean.lower() for tok in cand_tokens)
            if has_student_token:
                all_aliases_set.add(ea_clean)

    # Ne jamais remplacer l'alias lui-même, les préfixes ou des termes génériques
    all_aliases_set.discard(alias)
    all_aliases_set.discard("etudiant")
    all_aliases_set.discard("student")
    for g in GENERIC_PROTECTED_TERMS:
        all_aliases_set.discard(g)

    sorted_aliases = sorted(
        [a for a in all_aliases_set if len(a) >= 3 and a.lower() not in GENERIC_PROTECTED_TERMS],
        key=len,
        reverse=True,
    )

    # 3. Modification du contenu des fichiers
    for root, _, files in os.walk(student_dir):
        for file in files:
            if ":" in file or "Zone.Identifier" in file:
                continue
            file_path = os.path.join(root, file)
            _, ext = os.path.splitext(file.lower())

            if ext == ".docx":
                n_rep = anonymize_docx_file(file_path, alias, sorted_aliases, da)
                if n_rep > 0:
                    stats["files_modified"] += 1
            elif ext in TEXT_EXTENSIONS or ext == "":
                for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                    try:
                        with open(file_path, "r", encoding=encoding) as f:
                            text = f.read()
                        new_text, n_rep = anonymize_text_content(text, alias, sorted_aliases, da)
                        if n_rep > 0:
                            with open(file_path, "w", encoding=encoding) as f:
                                f.write(new_text)
                            stats["files_modified"] += 1
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                    except Exception:
                        break

    # 4. Renommage des fichiers et dossiers (topdown=False pour traiter les enfants avant parents)
    for root, dirs, files in os.walk(student_dir, topdown=False):
        for item in files + dirs:
            if ":" in item or "Zone.Identifier" in item:
                continue
            old_path = os.path.join(root, item)
            new_item = item

            # Remplacement des alias dans le nom (du plus long au plus court)
            for target in sorted_aliases:
                if not target or len(target) < 3:
                    continue
                pattern = re.compile(re.escape(target), re.IGNORECASE)
                new_item = pattern.sub(alias, new_item)

            # Remplacement du DA dans le nom
            if da and len(da) == 7:
                new_item = new_item.replace(da, "XXXXXXX")
            new_item = re.sub(r"\b\d{7}\b", "XXXXXXX", new_item)

            if new_item != item:
                new_path = os.path.join(root, new_item)
                target_path = new_path
                # Gestion anti-collision : si target_path existe déjà, ajouter un suffixe numérique
                if os.path.exists(target_path) and os.path.abspath(target_path) != os.path.abspath(old_path):
                    base_stem, ext = os.path.splitext(new_item)
                    counter = 1
                    while os.path.exists(target_path) and os.path.abspath(target_path) != os.path.abspath(old_path):
                        target_path = os.path.join(root, f"{base_stem}_{counter}{ext}")
                        counter += 1

                try:
                    os.rename(old_path, target_path)
                    stats["files_renamed"] += 1
                except Exception as e:
                    print(f"⚠ Impossible de renommer {old_path} vers {target_path}: {e}")

    # Nettoyage final des métadonnées résiduelles
    cleanup_metadata_files(student_dir)
    return stats
