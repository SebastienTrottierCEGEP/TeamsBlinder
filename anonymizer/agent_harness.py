"""
Agent Harness utilisant le Strands Agent SDK et Ollama.
Inspecte les dossiers de remises étudiants pour identifier et remplacer
les occurrences de noms (y compris variantes, fautes de frappe, courriels)
et de numéros DA (7 chiffres) dans les fichiers et noms de fichiers.
"""

import os
import re
from typing import Any, Callable, Dict, List, Optional

try:
    from strands import Agent, tool
    from strands.models.ollama import OllamaModel
    HAS_STRANDS = True
except ImportError:
    HAS_STRANDS = False


def create_anonymization_tools(base_dir: str):
    """Crée des outils Strands sécurisés limités au répertoire de travail."""
    abs_base = os.path.abspath(base_dir)

    def _is_safe_path(path: str) -> bool:
        return os.path.abspath(path).startswith(abs_base)

    if not HAS_STRANDS:
        return []

    @tool
    def list_files(folder_path: str) -> str:
        """
        Liste les fichiers présents dans un dossier de la remise étudiante.

        Args:
            folder_path: Chemin du dossier à inspecter.
        """
        if not _is_safe_path(folder_path) or not os.path.isdir(folder_path):
            return f"Erreur: dossier invalide ou inaccessible : {folder_path}"
        files = []
        for root, _, filenames in os.walk(folder_path):
            for fn in filenames:
                files.append(os.path.relpath(os.path.join(root, fn), abs_base))
        return "\n".join(files) if files else "Aucun fichier trouvé."

    @tool
    def read_file_content(file_path: str) -> str:
        """
        Lit le contenu d'un fichier textuel ou de code source pour repérer des mentions de l'étudiant.

        Args:
            file_path: Chemin du fichier à lire.
        """
        full_p = os.path.join(abs_base, file_path) if not os.path.isabs(file_path) else file_path
        if not _is_safe_path(full_p) or not os.path.isfile(full_p):
            return f"Erreur: fichier inaccessible : {file_path}"
        try:
            with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(4000)  # Limite à 4000 caractères pour efficacité
            return content
        except Exception as e:
            return f"Erreur de lecture: {e}"

    @tool
    def rename_file(old_path: str, new_path: str) -> str:
        """
        Renomme un fichier ou un dossier pour remplacer le nom de l'étudiant par son pseudonyme.

        Args:
            old_path: Ancien chemin du fichier.
            new_path: Nouveau chemin du fichier après anonymisation.
        """
        full_old = os.path.join(abs_base, old_path) if not os.path.isabs(old_path) else old_path
        full_new = os.path.join(abs_base, new_path) if not os.path.isabs(new_path) else new_path

        if not _is_safe_path(full_old) or not _is_safe_path(full_new):
            return "Erreur: chemin hors du dossier autorisé."
        if not os.path.exists(full_old):
            return f"Erreur: {old_path} n'existe pas."
        try:
            os.rename(full_old, full_new)
            return f"Succès: {old_path} renommé en {new_path}"
        except Exception as e:
            return f"Erreur lors du renommage: {e}"

    @tool
    def replace_text_in_file(file_path: str, text_to_replace: str, replacement_text: str) -> str:
        """
        Remplace une chaîne de caractères (nom ou DA) dans un fichier par son texte anonymisé.

        Args:
            file_path: Chemin du fichier à modifier.
            text_to_replace: Texte original à supprimer (ex: 'Gaetan Simard', '2244612').
            replacement_text: Texte de remplacement (ex: 'etudiant01', 'XXXXXXX').
        """
        full_p = os.path.join(abs_base, file_path) if not os.path.isabs(file_path) else file_path
        if not _is_safe_path(full_p) or not os.path.isfile(full_p):
            return f"Erreur: fichier inaccessible : {file_path}"
        try:
            with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if text_to_replace in content:
                new_content = content.replace(text_to_replace, replacement_text)
                with open(full_p, "w", encoding="utf-8") as f:
                    f.write(new_content)
                return f"Succès: '{text_to_replace}' remplacé par '{replacement_text}' dans {file_path}."
            return f"Notice: '{text_to_replace}' non trouvé dans {file_path}."
        except Exception as e:
            return f"Erreur lors du remplacement: {e}"

    return [list_files, read_file_content, rename_file, replace_text_in_file]


class AnonymizationAgentHarness:
    """
    Harness pilotant l'agent Strands pour rechercher et anonymiser
    les mentions de l'étudiant dans sa remise.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model_id: str = "llama3.2:3b",
        callback_handler: Optional[Callable[..., Any]] = None,
    ):
        self.host = host
        self.model_id = model_id
        self.callback_handler = callback_handler

    def process_student_directory(
        self,
        student_dir: str,
        student_name: str,
        da: str,
        alias: str,
    ) -> bool:
        """
        Invoque l'agent Strands pour analyser et anonymiser la remise d'un étudiant.
        """
        if not HAS_STRANDS:
            print("⚠ Strands SDK non disponible, exécution du mode déterministe uniquement.")
            return False

        tools = create_anonymization_tools(student_dir)
        try:
            model = OllamaModel(host=self.host, model_id=self.model_id)
            agent_kwargs: Dict[str, Any] = {"model": model, "tools": tools}
            if self.callback_handler:
                agent_kwargs["callback_handler"] = self.callback_handler

            agent = Agent(**agent_kwargs)

            prompt = (
                f"Tu es un assistant chargé d'anonymiser rigoureusement une remise d'examen étudiante.\n"
                f"Identité de l'étudiant à anonymiser :\n"
                f"- Nom complet : {student_name}\n (et toutes ses variantes - certains étudiants ont des noms de famille composés et/ou plusieurs prénoms)\n"
                f"- DA (numéro d'étudiant) : {da if da else 'Inconnu'}\n"
                f"- Pseudonyme de remplacement : {alias}\n"
                f"- Remplacement pour tout DA de 7 chiffres : XXXXXXX\n\n"
                f"Tâches à accomplir dans le dossier '{student_dir}' :\n"
                f"1. Utilise 'list_files' pour découvrir tous les fichiers.\n"
                f"2. Renomme tout fichier ou dossier dont le nom contient le nom de l'étudiant (y compris avec fautes de frappe, inversions de prénom(s) et nom(s), omission de certains prénoms on noms, utilisation d'initiales) pour utiliser '{alias}'.\n"
                f"3. Lis les fichiers et remplace toute mention du nom de l'étudiant (y compris avec fautes de frappe, inversions de prénom(s) et nom(s), omission de certains prénoms on noms, utilisation d'initiales) par '{alias}' et tout numéro DA (7 chiffres) par 'XXXXXXX'.\n"
                f"Confirme dès que l'anonymisation est complète."
            )

            agent(prompt)
            return True
        except Exception as e:
            print(f"⚠ L'agent Strands a rencontré une erreur ({e}). Le moteur déterministe prend le relais.")
            return False
