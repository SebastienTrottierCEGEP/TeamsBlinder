"""
Agent Harness utilisant le Strands Agent SDK et Ollama.
Inspecte les dossiers de remises étudiants pour identifier et remplacer
les occurrences de noms (y compris variantes, fautes de frappe, courriels)
et de numéros DA (7 chiffres) dans les fichiers et noms de fichiers.
"""

import os
import re
from typing import Any, Callable, Dict, List, Optional

from anonymizer.config import load_config

try:
    from strands import Agent, tool
    from strands.models.ollama import OllamaModel
    HAS_STRANDS = True

    class SafeOllamaModel(OllamaModel):
        """
        OllamaModel tolérant aux compteurs absents.
        Ollama renvoie None pour prompt_eval_count (prompt en cache) ou eval_count,
        ce qui fait échouer l'addition des métriques dans Strands.
        """

        def format_chunk(self, event: Dict[str, Any]):
            if event.get("chunk_type") == "metadata":
                data = event["data"]
                for attr in ("prompt_eval_count", "eval_count", "total_duration"):
                    if getattr(data, attr, 0) is None:
                        setattr(data, attr, 0)
            return super().format_chunk(event)
except ImportError:
    HAS_STRANDS = False


class AgentLoopLimitError(RuntimeError):
    """Levée lorsque l'agent dépasse ses limites de tours ou d'appels d'outils."""


class AgentLoopGuard:
    """Compte les tours et appels d'outils, et détecte les appels identiques répétés."""

    def __init__(self, max_turns: int = 30, max_tool_calls: int = 60, max_repeated_calls: int = 3):
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.max_repeated_calls = max_repeated_calls
        self.turns = 0
        self.tool_calls = 0
        self.reason: Optional[str] = None
        self._signatures: Dict[Any, int] = {}

    def record_turn(self) -> None:
        self.turns += 1
        if self.turns > self.max_turns and not self.reason:
            self.reason = f"limite de {self.max_turns} tours dépassée"

    def record_tool_call(self, name: str, *args: Any) -> Optional[str]:
        """Enregistre un appel d'outil; retourne un message d'arrêt si une limite est atteinte."""
        self.tool_calls += 1
        signature = (name, args)
        self._signatures[signature] = self._signatures.get(signature, 0) + 1
        if not self.reason:
            if self.tool_calls > self.max_tool_calls:
                self.reason = f"limite de {self.max_tool_calls} appels d'outils dépassée"
            elif self._signatures[signature] > self.max_repeated_calls:
                self.reason = f"appel identique à '{name}' répété plus de {self.max_repeated_calls} fois"
        if self.reason:
            return f"Erreur: arrêt demandé ({self.reason}). Cesse tout appel d'outil et termine ta réponse."
        return None

    def check(self) -> None:
        if self.reason:
            raise AgentLoopLimitError(self.reason)


def create_anonymization_tools(base_dir: str, guard: Optional[AgentLoopGuard] = None):
    """Crée des outils Strands sécurisés limités au répertoire de travail."""
    abs_base = os.path.abspath(base_dir)
    guard = guard or AgentLoopGuard()

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
        if stop := guard.record_tool_call("list_files", folder_path):
            return stop
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
        if stop := guard.record_tool_call("read_file_content", file_path):
            return stop
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
        if stop := guard.record_tool_call("rename_file", old_path, new_path):
            return stop
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
        if stop := guard.record_tool_call("replace_text_in_file", file_path, text_to_replace, replacement_text):
            return stop
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
        model_id: Optional[str] = None,
        callback_handler: Optional[Callable[..., Any]] = None,
        max_turns: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_repeated_calls: Optional[int] = None,
    ):
        config = load_config()
        self.host = host
        self.model_id = model_id if model_id is not None else config["model_id"]
        self.callback_handler = callback_handler
        self.max_turns = max_turns if max_turns is not None else int(config["agent_max_turns"])
        self.max_tool_calls = max_tool_calls if max_tool_calls is not None else int(config["agent_max_tool_calls"])
        self.max_repeated_calls = (
            max_repeated_calls if max_repeated_calls is not None else int(config["agent_max_repeated_calls"])
        )

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

        guard = AgentLoopGuard(self.max_turns, self.max_tool_calls, self.max_repeated_calls)
        tools = create_anonymization_tools(student_dir, guard)
        user_callback = self.callback_handler

        def guarded_callback(**event: Any) -> None:
            if event.get("start_event_loop"):
                guard.record_turn()
            guard.check()
            if user_callback:
                user_callback(**event)

        try:
            model = SafeOllamaModel(host=self.host, model_id=self.model_id)
            agent = Agent(model=model, tools=tools, callback_handler=guarded_callback)

            '''
            STROTTIER Bug avec llama3.2:3b: stdout:
            * GordonManninghamEvelyne-Markdown.png -> etudiant09_Markdown.png
            * GordonManninghamEvelyne-Texte.png -> etudiant09_Texte.png
            * GordonManninghamEvelyne-NomZone.png -> etudiant09_NomZone.png
            * GordonManninghamEvelyne-personne.png -> etudiant09_personne.png
            * automations (1).yaml -> automations (1).yaml (aucune modification)
            * GordonManninghamEvelyne-Lovelace.txt -> etudiant09_Lovelace.txt

            fichiers resultants dans le dossier de l'étudiant après anonymisation:
            ...
            etudiant09-ManninghamEvelyne-Lovelace.txt (comme si seul le nom de famille avait été remplacé, mais pas le prénom)

            '''
            prompt = (
                f"Tu es un assistant chargé d'anonymiser rigoureusement une remise d'examen étudiante.\n"
                f"Identité de l'étudiant à anonymiser :\n"
                f"- Nom de l'étudiant : {student_name}\n (et toutes ses variantes - certains étudiants ont des noms de famille composés et/ou plusieurs prénoms)\n"
                f"- DA (numéro d'étudiant) : {da if da else 'Inconnu'}\n"
                f"- Pseudonyme de remplacement : {alias}\n"
                f"- Remplacement pour tout DA de 7 chiffres : XXXXXXX\n\n"
                f"Variantes du nom de l'étudiant à prendre en compte :\n"
                    "1. Name Order Flips: (e.g., \"Smith, John\" vs. \"John Smith\")\n"
                    "2. Initials & Truncations: (e.g., \"J. Smith\", \"J.H. Smith\", \"John S.\")\n"
                    "3. Nicknames & Diminutives: (e.g., \"Bob\" for \"Robert\", \"Liz\" for \"Elizabeth\")\n"
                    "4. Phonetic & Transliteration Variations: (e.g., \"Mohammad\" vs. \"Muhammad\" vs. \"Mohamed\")\n"
                    "5. Typos & Misspellings: Common OCR or keystroke errors (e.g., \"Jhon\", \"Smiht\")\n"
                    "6. Honorifics, Titles, & Suffixes: (e.g., \"Dr. Smith\", \"John Smith Jr.\", \"Prof. J. Smith\")\n"
                    "7. Compound & Hyphenated Forms...\n"
                    "8. Removal of whitespace\n"
                f"Tâches à accomplir dans le dossier '{student_dir}' :\n"
                f"1. Utilise 'list_files' pour découvrir tous les fichiers.\n"
                f"2. Renomme tout fichier ou dossier dont le nom contient une variante du nom de l'étudiant (y compris avec fautes de frappe, inversions de prénom(s) et nom(s), omission de certains prénoms on noms, utilisation d'initiales) pour utiliser '{alias}'.\n"
                f"3. Lis les fichiers et remplace toute mention du nom de l'étudiant (y compris avec fautes de frappe, inversions de prénom(s) et nom(s), omission de certains prénoms on noms, utilisation d'initiales) par '{alias}' et tout numéro DA (7 chiffres) par 'XXXXXXX'.\n"
                f"Confirme dès que l'anonymisation est complète."
            )

            agent(prompt)
            guard.check()
            return True
        except AgentLoopLimitError as e:
            print(
                f"⚠ Agent Strands interrompu ({e}; {guard.turns} tour(s), {guard.tool_calls} appel(s) d'outils). "
                "Le moteur déterministe prend le relais."
            )
            return False
        except Exception as e:
            print(f"⚠ L'agent Strands a rencontré une erreur ({e}). Le moteur déterministe prend le relais.")
            return False
