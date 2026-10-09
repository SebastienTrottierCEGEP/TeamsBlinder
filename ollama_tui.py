#!/usr/bin/env python3
"""
Ollama Model Manager TUI
Application terminal interactive pour visualiser et supprimer les modèles Ollama locaux.
"""

import curses
import json
import math
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime

OLLAMA_HOST = "http://localhost:11434"


def format_size(bytes_val):
    """Convertit un nombre d'octets en chaîne lisible (Go, Mo, etc.)."""
    if not bytes_val or bytes_val <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(bytes_val, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_val / p, 2)
    return f"{s} {units[i]}"


def format_date(iso_str):
    """Formate une date ISO 8601 en date courte."""
    if not iso_str:
        return "-"
    try:
        clean_str = iso_str.split(".")[0].replace("Z", "")
        dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16]


def get_models(host=OLLAMA_HOST):
    """Récupère la liste des modèles locaux depuis l'API Ollama ou via la CLI."""
    # 1. Tentative via API HTTP
    try:
        req = urllib.request.Request(f"{host}/api/tags", headers={"User-Agent": "OllamaTUI"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            formatted = []
            for m in models:
                details = m.get("details", {}) or {}
                formatted.append({
                    "name": m.get("name", "inconnu"),
                    "size": format_size(m.get("size", 0)),
                    "params": details.get("parameter_size", "-"),
                    "quant": details.get("quantization_level", "-"),
                    "format": details.get("format", "-"),
                    "modified": format_date(m.get("modified_at", "")),
                })
            return formatted, "online", None
    except Exception as api_err:
        # 2. Fallback via la commande CLI `ollama list`
        try:
            res = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
            lines = res.stdout.strip().splitlines()
            if len(lines) > 1:
                formatted = []
                for line in lines[1:]:
                    parts = line.split()
                    if parts:
                        name = parts[0]
                        size = f"{parts[2]} {parts[3]}" if len(parts) >= 4 else "-"
                        formatted.append({
                            "name": name,
                            "size": size,
                            "params": "-",
                            "quant": "-",
                            "format": "-",
                            "modified": parts[-2] + " " + parts[-1] if len(parts) >= 6 else "-",
                        })
                return formatted, "cli_fallback", None
            return [], "online", None
        except Exception:
            return [], "offline", str(api_err)


def delete_model(model_name, host=OLLAMA_HOST):
    """Supprime un modèle via l'API Ollama ou via `ollama rm`."""
    # 1. Tentative API HTTP DELETE
    try:
        req = urllib.request.Request(
            f"{host}/api/delete",
            data=json.dumps({"name": model_name}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "OllamaTUI"},
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                return True, f"Modèle '{model_name}' supprimé avec succès."
    except Exception:
        pass

    # 2. Fallback CLI `ollama rm`
    try:
        res = subprocess.run(["ollama", "rm", model_name], capture_output=True, text=True)
        if res.returncode == 0:
            return True, f"Modèle '{model_name}' supprimé via CLI."
        return False, res.stderr.strip() or "Erreur inconnue lors de la suppression."
    except Exception as e:
        return False, str(e)


def draw_confirm_dialog(stdscr, model_name, model_size):
    """Affiche une boîte de dialogue modale pour confirmer la suppression."""
    h, w = stdscr.getmaxyx()
    box_h = 10
    box_w = min(64, w - 4)
    start_y = max(0, (h - box_h) // 2)
    start_x = max(0, (w - box_w) // 2)

    win = curses.newwin(box_h, box_w, start_y, start_x)
    win.keypad(True)

    # Couleurs
    curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_WHITE)

    while True:
        win.erase()
        win.box()
        title = " CONFIRMATION DE SUPPRESSION "
        win.addstr(0, max(2, (box_w - len(title)) // 2), title, curses.color_pair(10) | curses.A_BOLD)

        msg1 = "Voulez-vous vraiment supprimer ce modèle local ?"
        win.addstr(2, max(2, (box_w - len(msg1)) // 2), msg1)

        name_str = f"Modèle : {model_name}"
        if len(name_str) > box_w - 4:
            name_str = name_str[:box_w - 7] + "..."
        win.addstr(4, max(2, (box_w - len(name_str)) // 2), name_str, curses.A_BOLD)

        size_str = f"Espace disque qui sera libéré : {model_size}"
        win.addstr(5, max(2, (box_w - len(size_str)) // 2), size_str, curses.A_DIM)

        prompt = " [O] Oui, supprimer     [N / Échap] Annuler "
        win.addstr(7, max(2, (box_w - len(prompt)) // 2), prompt, curses.color_pair(11) | curses.A_BOLD)

        win.refresh()
        key = win.getch()

        if key in (ord("o"), ord("O"), ord("y"), ord("Y"), 10, 13):
            return True
        elif key in (ord("n"), ord("N"), 27, ord("q"), ord("Q")):
            return False


def main_tui(stdscr):
    # Configuration curses
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.use_default_colors()

    # Paires de couleurs
    curses.init_pair(1, curses.COLOR_CYAN, -1)     # Titre
    curses.init_pair(2, curses.COLOR_GREEN, -1)    # Statut en ligne
    curses.init_pair(3, curses.COLOR_RED, -1)      # Erreur / hors ligne
    curses.init_pair(4, curses.COLOR_YELLOW, -1)   # Attention
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Sélection curseur
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)  # En-tête de tableau

    selected_idx = 0
    message = ""
    message_type = "info"  # "info", "success", "error"

    models, status, err = get_models()

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        if h < 14 or w < 65:
            stdscr.addstr(0, 0, "Fenêtre trop petite. Veuillez agrandir le terminal (min 65x14).")
            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord("q"), ord("Q"), 27):
                break
            continue

        # 1. En-tête supérieur
        app_title = " 🦙 OLLAMA MODEL MANAGER - TUI "
        stdscr.addstr(1, 2, app_title, curses.color_pair(1) | curses.A_BOLD)

        # Statut du serveur
        if status == "online":
            status_text = "● Serveur actif (http://localhost:11434)"
            stdscr.addstr(1, max(35, w - len(status_text) - 4), status_text, curses.color_pair(2) | curses.A_BOLD)
        elif status == "cli_fallback":
            status_text = "● Mode CLI (API non joignable)"
            stdscr.addstr(1, max(35, w - len(status_text) - 4), status_text, curses.color_pair(4) | curses.A_BOLD)
        else:
            status_text = "● Serveur hors ligne"
            stdscr.addstr(1, max(35, w - len(status_text) - 4), status_text, curses.color_pair(3) | curses.A_BOLD)

        stdscr.addstr(2, 2, "─" * (w - 4), curses.A_DIM)

        # 2. Statistiques et compteur
        nb_models = len(models)
        count_str = f"Modèles installés : {nb_models}"
        stdscr.addstr(3, 2, count_str, curses.A_BOLD)

        # Message temporaire s'il existe
        if message:
            msg_color = curses.color_pair(2) if message_type == "success" else curses.color_pair(3)
            # Tronquer le message si trop long
            max_msg_len = w - len(count_str) - 8
            display_msg = message[:max_msg_len]
            stdscr.addstr(3, len(count_str) + 6, display_msg, msg_color | curses.A_BOLD)

        # 3. En-têtes du tableau
        header_y = 5
        col_name_w = max(24, w - 48)
        table_header = f" {'#':<3} {'NOM DU MODÈLE':<{col_name_w}} {'TAILLE':<10} {'PARAMS':<8} {'QUANT':<7} "
        table_header_padded = table_header.ljust(w - 4)
        stdscr.addstr(header_y, 2, table_header_padded[:w - 4], curses.color_pair(6) | curses.A_BOLD)

        # 4. Liste des modèles
        list_y_start = 6
        visible_rows = h - list_y_start - 3

        if not models:
            if status == "offline":
                stdscr.addstr(list_y_start + 2, 4, "Impossible de joindre Ollama.", curses.color_pair(3))
                stdscr.addstr(list_y_start + 3, 4, "Vérifiez que le serveur est démarré avec './setup_wsl.sh'.", curses.A_DIM)
            else:
                stdscr.addstr(list_y_start + 2, 4, "Aucun modèle local trouvé.", curses.color_pair(4))
                stdscr.addstr(list_y_start + 3, 4, "Téléchargez un modèle avec 'ollama pull llama3.1'.", curses.A_DIM)
        else:
            # Gestion du défilement
            if selected_idx >= nb_models:
                selected_idx = max(0, nb_models - 1)

            scroll_offset = max(0, selected_idx - visible_rows + 1)

            for i in range(visible_rows):
                model_idx = scroll_offset + i
                if model_idx >= nb_models:
                    break

                m = models[model_idx]
                curr_y = list_y_start + i
                is_selected = (model_idx == selected_idx)

                row_str = f" {model_idx + 1:<3} {m['name']:<{col_name_w}} {m['size']:<10} {m['params']:<8} {m['quant']:<7} "
                row_str_padded = row_str.ljust(w - 4)

                if is_selected:
                    stdscr.addstr(curr_y, 2, row_str_padded[:w - 4], curses.color_pair(5) | curses.A_BOLD)
                else:
                    attr = curses.A_NORMAL if (i % 2 == 0) else curses.A_DIM
                    stdscr.addstr(curr_y, 2, row_str_padded[:w - 4], attr)

        # 5. Barre de navigation et raccourcis en bas
        footer_y = h - 2
        stdscr.addstr(footer_y - 1, 2, "─" * (w - 4), curses.A_DIM)
        shortcuts = " [↑/↓ ou j/k] Naviguer   [d / Suppr] Effacer   [r] Rafraîchir   [q / Échap] Quitter"
        stdscr.addstr(footer_y, 2, shortcuts[:w - 4], curses.color_pair(1))

        stdscr.refresh()

        # Lecture de la touche utilisateur
        key = stdscr.getch()

        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (curses.KEY_UP, ord("k"), ord("K")):
            if nb_models > 0:
                selected_idx = (selected_idx - 1) % nb_models
        elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
            if nb_models > 0:
                selected_idx = (selected_idx + 1) % nb_models
        elif key in (ord("r"), ord("R")):
            message = "Actualisation..."
            message_type = "info"
            models, status, err = get_models()
            message = "Liste actualisée."
            message_type = "success"
        elif key in (ord("d"), ord("D"), curses.KEY_DC, ord("\x7f")):
            if nb_models > 0 and selected_idx < nb_models:
                target_model = models[selected_idx]
                confirmed = draw_confirm_dialog(stdscr, target_model["name"], target_model["size"])
                if confirmed:
                    success, msg = delete_model(target_model["name"])
                    if success:
                        message = f"✔ {target_model['name']} supprimé."
                        message_type = "success"
                        models, status, err = get_models()
                        if selected_idx >= len(models):
                            selected_idx = max(0, len(models) - 1)
                    else:
                        message = f"❌ Erreur : {msg}"
                        message_type = "error"
                else:
                    message = "Suppression annulée."
                    message_type = "info"


def main():
    try:
        curses.wrapper(main_tui)
    except KeyboardInterrupt:
        pass
    print("Application Ollama TUI fermée.\n")


if __name__ == "__main__":
    main()
