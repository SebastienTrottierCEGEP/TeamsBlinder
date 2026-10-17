"""
Agent Harness utilisant le Strands Agent SDK et Ollama.
Analyse le manifeste des noms de fichiers et des extraits de code d'une remise
pour identifier intelligemment les alias contextuels, usernames, entités et fautes de frappe.
"""

import json
import os
import re
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from anonymizer.config import load_config

try:
    from strands import Agent
    from strands.models.ollama import OllamaModel
    HAS_STRANDS = True
except ImportError:
    HAS_STRANDS = False


class AgentLoopLimitError(RuntimeError):
    """Erreur levée lorsque l'agent dépasse ses limites de boucle ou d'appels répétitifs."""
    pass


class AgentLoopGuard:
    """Garde-fou empêchant les boucles infinies ou les appels d'outils répétitifs."""

    def __init__(
        self,
        max_turns: int = 10,
        max_tool_calls: int = 20,
        max_repeated_calls: int = 3,
    ):
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.max_repeated_calls = max_repeated_calls
        self.turns = 0
        self.tool_calls_count = 0
        self.call_history: List[tuple] = []
        self.tripped = False
        self.trip_reason = ""

    def record_turn(self) -> None:
        self.turns += 1
        if self.turns > self.max_turns:
            self.tripped = True
            self.trip_reason = f"Nombre maximal de tours dépassé : {self.turns} > {self.max_turns}"

    def record_tool_call(self, name: str, *args) -> Optional[str]:
        self.tool_calls_count += 1
        call_sig = (name, tuple(str(a) for a in args))
        self.call_history.append(call_sig)

        # Vérification des appels identiques consécutifs
        recent_identical = 0
        for item in reversed(self.call_history):
            if item == call_sig:
                recent_identical += 1
            else:
                break

        if recent_identical > self.max_repeated_calls:
            self.tripped = True
            self.trip_reason = f"Appels identiques répétés : {recent_identical} > {self.max_repeated_calls}"
            return self.trip_reason

        if self.tool_calls_count > self.max_tool_calls:
            self.tripped = True
            self.trip_reason = f"Nombre maximal d'appels d'outils dépassé : {self.tool_calls_count} > {self.max_tool_calls}"
            return self.trip_reason

        return None

    def check(self) -> None:
        if self.tripped:
            raise AgentLoopLimitError(self.trip_reason)


class AnonymizationAgentHarness:
    """
    Harness pilotant l'agent Strands pour rechercher et extraire
    les variantes, alias et identifiants de l'étudiant à partir du manifeste de sa remise.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        model_id: Optional[str] = None,
        callback_handler: Optional[Callable[..., Any]] = None,
    ):
        cfg = load_config()
        self.host = host or cfg.get("host", "http://localhost:11434")
        self.model_id = model_id or cfg.get("model_id", "llama3.2:3b")
        self.max_turns = int(cfg.get("agent_max_turns", 10))
        self.max_tool_calls = int(cfg.get("agent_max_tool_calls", 20))
        self.max_repeated_calls = int(cfg.get("agent_max_repeated_calls", 3))
        self.callback_handler = callback_handler

    def check_availability(self, timeout: float = 3.0) -> tuple:
        """
        Vérifie si le serveur Ollama est actif et répond rapidement.
        Retourne (True, 'version X.Y.Z') ou (False, 'message d'erreur').
        """
        # 1. Vérification de l'endpoint /api/version
        try:
            req = urllib.request.Request(
                f"{self.host.rstrip('/')}/api/version",
                headers={"User-Agent": "TeamsBlinderAgent"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    version = data.get("version", "actif")
                    return True, f"version {version}"
        except Exception as e:
            # 2. Deuxième tentative sur la racine /
            try:
                req_root = urllib.request.Request(
                    f"{self.host.rstrip('/')}/",
                    headers={"User-Agent": "TeamsBlinderAgent"},
                )
                with urllib.request.urlopen(req_root, timeout=timeout) as resp:
                    if resp.status == 200:
                        return True, "en ligne"
            except Exception:
                pass
            return False, f"injoignable ({e})"

        return False, "injoignable"

    def is_available(self, timeout: float = 3.0) -> bool:
        """Retourne True si le serveur Ollama répond, False sinon."""
        available, _ = self.check_availability(timeout=timeout)
        return available

    def discover_aliases(
        self,
        student_name: str,
        da: str,
        alias: str,
        filenames: List[str],
        snippets: List[str],
    ) -> List[str]:
        """
        Interroge l'agent Strands / Ollama avec le manifeste complet de la remise
        pour découvrir tous les alias, identifiants d'entités et variantes du nom.
        Retourne la liste des alias identifiés.
        Ne tente rien si Ollama ne répond pas.
        """
        # Ne pas tenter l'utilisation d'Ollama s'il ne répond pas
        if not self.is_available(timeout=2.0):
            return []

        files_preview = "\n".join(f"- {f}" for f in filenames[:50])
        if len(filenames) > 50:
            files_preview += f"\n... et {len(filenames) - 50} autres fichiers."

        snippets_preview = "\n".join(f"- {s}" for s in snippets[:40]) if snippets else "Aucun extrait textuel particulier."

        prompt = (
            f"Tu es un expert en anonymisation de devoirs informatiques d'étudiants.\n"
            f"Nous devons identifier UNIQUEMENT les chaînes correspondant à l'identité de l'étudiant suivant :\n"
            f"- Nom officiel : {student_name}\n"
            f"- DA : {da if da else 'Inconnu'}\n"
            f"- Pseudonyme : {alias}\n\n"
            f"Voici les fichiers de sa remise :\n"
            f"{files_preview}\n\n"
            f"Voici des extraits de code et configuration :\n"
            f"{snippets_preview}\n\n"
            f"Consignes STRICTES :\n"
            f"1. Retourne UNIQUEMENT les variations et fautes de frappe du nom de l'étudiant (ex: CharlesMandla, Gatean au lieu de Gaetan) "
            f"et les entités contenant son nom ou ses initiales (ex: notify.amadi_bernouilli_amadi, person.mathieu_roberge_girardeau, it17poly_mathieu_r_g_it17).\n"
            f"2. N'inclus JAMAIS de termes génériques ou fichiers standards du cours (ex: automations, configuration, scripts, known_devices, device_tracker, person, notify, TableauDeBord, Lovelace, Olaf, etc.).\n"
            f"3. Réponds UNIQUEMENT un objet JSON avec la clé 'aliases'.\n"
            f"Exemple : {{\"aliases\": [\"{student_name}\", \"NomPrenom\"]}}\n"
        )

        discovered = []

        # 1. Tentative avec Strands Agent SDK si disponible (format JSON contraint)
        if HAS_STRANDS:
            try:
                model = OllamaModel(
                    host=self.host,
                    model_id=self.model_id,
                    max_tokens=256,
                    temperature=0.1,
                    additional_args={"format": "json"},
                    options={"num_predict": 256, "temperature": 0.1},
                    ollama_client_args={"timeout": 15.0},
                )
                agent_kwargs = {"model": model}
                if self.callback_handler:
                    agent_kwargs["callback_handler"] = self.callback_handler
                agent = Agent(**agent_kwargs)
                response = agent(prompt)
                raw_text = str(response)
                discovered = self._extract_json_aliases(raw_text)
                if discovered:
                    return discovered
            except Exception:
                pass

        # 2. Fallback direct via l'API Ollama (format JSON strict, timeout 15s)
        try:
            req_data = {
                "model": self.model_id,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 256,
                },
            }
            req = urllib.request.Request(
                f"{self.host.rstrip('/')}/api/generate",
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "TeamsBlinderAgent"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_str = data.get("response", "")
                discovered = self._extract_json_aliases(response_str)
        except Exception:
            pass

        return discovered

    def _extract_json_aliases(self, text: str) -> List[str]:
        """Extrait la liste d'alias depuis une réponse JSON ou du texte formaté."""
        if not text:
            return []

        parsed = None
        try:
            parsed = json.loads(text.strip())
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except Exception:
                    pass

        if isinstance(parsed, dict) and "aliases" in parsed:
            raw_list = parsed["aliases"]
            if isinstance(raw_list, list):
                clean_items = []
                known_exts = {".yaml", ".yml", ".txt", ".png", ".jpg", ".jpeg", ".zip", ".docx"}
                for item in raw_list:
                    item_str = str(item).strip("\"' \t\r\n")
                    if len(item_str) >= 3:
                        clean_items.append(item_str)
                        base_name = os.path.basename(item_str)
                        stem, ext = os.path.splitext(base_name)
                        if ext.lower() in known_exts and len(stem) >= 3 and stem != item_str:
                            clean_items.append(stem)
                return clean_items

        return []
