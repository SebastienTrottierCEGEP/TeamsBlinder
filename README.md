# TeamsBlinder - Anonymisation d'Examens Étudiants avec Strands Agent SDK & Ollama

**TeamsBlinder** est un outil complet d'anonymisation pour les examens et devoirs étudiants soumis via Microsoft Teams (ou plateformes similaires).
Il s'appuie sur une approche hybride robuste combinant des règles déterministes et un **Agent Harness** propulsé par **Strands Agent SDK** et un modèle local **Ollama** (ex: `llama3.2:3b` ou `llama3.1`).

---

## 🎯 Fonctionnalités principales

1. **Extraction automatique d'identité** : Détecte le nom complet et le **DA** (7 chiffres) à partir de formats courants de répertoires Teams (ex: `Gaetan Simard (2244612)`).
2. **Attribution de pseudonymes séquentiels** : Génère des alias uniques (`etudiant01`, `etudiant02`, ...) pour chaque étudiant.
3. **Fichier central de traçabilité** : Consigne dans `mapping_central.csv` la correspondance sécurisée entre le nom d'origine, le DA, le pseudonyme attribué, les dossiers et la date.
4. **Filtrage intelligent des versions** : Identifie les dossiers ou remises `Version 1`, `Version 2`, etc., retient automatiquement **la version la plus récente** (`Version N` max) et élimine les versions antérieures.
5. **Décompression des archives** : Extrait récursivement les fichiers `.zip` et supprime l'archive originale afin de ne laisser aucun contenu non anonymisé.
6. **Agent Harness (Strands + Ollama)** :
   - Analyse les fichiers et dossiers pour repérer les noms d'étudiants, variations compactées, inversions (NomPrenom / PrenomNom) et fautes de frappe.
   - Renomme les fichiers/dossiers (ex: `submission._GateanSimard.txt` -> `submission._etudiant01.txt`).
   - Remplace dans les contenus textuels et code source le nom par le pseudonyme et tout DA (7 chiffres) par `XXXXXXX`.

---

## 📁 Structure du projet

- **`anonymize_exams.py`** : Point d'entrée principal pour lancer l'anonymisation.
- **`run_anonymizer.sh`** : Script bash pour lancer l'anonymisation dans WSL.
- **`anonymizer/`** :
  - `config.py` : Chargement et validation de `config.properties`.
  - `identity.py` : Extraction de nom/DA et gestion du fichier central `mapping_central.csv`.
  - `file_operations.py` : Gestion des versions, copie, décompression `.zip`, renommage et remplacement textuel.
  - `agent_harness.py` : Agent Strands avec outils (`list_files`, `read_file_content`, `rename_file`, `replace_text_in_file`).
- **`config.properties`** : Fichier central de configuration.
- **`manage_models.sh`** / **`ollama_tui.py`** : Interface TUI pour visualiser, choisir et supprimer les modèles locaux.
- **`setup_wsl.sh`** : Installation et configuration d'Ollama et du venv sous WSL.
- **`stop_ollama.sh`** : Arrêt propre d'Ollama pour libérer la VRAM GPU.
- **`tests/test_anonymizer.py`** : Suite de tests unitaires.

---

## ⚙️ Configuration (`config.properties`)

```properties
# ==============================================================================
# Configuration Strands & Ollama
# ==============================================================================
# Modèle adapté pour 4GB VRAM (avec support des outils)
model_id=llama3.2:3b
host=http://localhost:11434

# ==============================================================================
# Configuration Anonymisation d'Examens (TeamsBlinder)
# ==============================================================================
# Dossier source contenant les répertoires étudiants
submissions_base_path=./SampleDir

# Nom de l'évaluation ou examen ciblé dans le sous-dossier de chaque étudiant
exam_name=Objets Connectés 1 - Examen 1

# Dossier destination recevant les remises anonymisées
anonymized_base_path=./SampleDir_Anonymise

# Préfixe pour le nom de remplacement (ex: etudiant -> etudiant01, etudiant02)
replacement_prefix=etudiant

# Fichier central de traçabilité (Nom d'origine, DA, Alias)
mapping_file=./SampleDir_Anonymise/mapping_central.csv
```

---

## 🚀 Utilisation sous WSL

### 1. Lancer l'anonymisation

```bash
chmod +x run_anonymizer.sh
./run_anonymizer.sh
```

*(ou directement avec python dans l'environnement virtuel) :*
```bash
python3 anonymize_exams.py
```

### 2. Dé-anonymiser un fichier (notes, commentaires, code)

Génère automatiquement `<nom_fichier>_out.<ext>` en remplaçant les `etudiantXX` par les vrais noms et les `XXXXXXX` par les vrais codes DA :

```bash
chmod +x deanonymize.sh
./deanonymize.sh notes_examen.csv
# -> Génère notes_examen_out.csv
```

Options disponibles :
- `-o <fichier_sortie>` : Spécifier un chemin de sortie personnalisé.
- `-m <mapping.csv>` : Spécifier un fichier de mapping alternatif.
- `--append-da` : Ajoute systématiquement le DA entre parenthèses après le nom (`Nom (DA)`).

### 3. Lancer les tests unitaires

```bash
python3 -m unittest discover tests
```

### 3. Gérer les modèles Ollama (TUI)

```bash
./manage_models.sh
```

### 4. Arrêter Ollama (libérer la VRAM)

```bash
./stop_ollama.sh
```
