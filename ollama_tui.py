#!/usr/bin/env python3
"""
Ollama Model Manager TUI
Application terminal interactive pour visualiser, sélectionner et supprimer les modèles Ollama locaux.
"""

import curses
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime

OLLAMA_HOST = "http://localhost:11434"
CONFIG_FILE = "config.properties"


def get_active_model_from_props(filepath=CONFIG_FILE):
    """Lit le nom du modèle configuré dans config.properties."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.join(script_dir, filepath) if not os.path.isabs(filepath) else filepath
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == "model_id":
                        return v.strip()
    return "llama3.1"


def set_active_model_in_props(model_name, filepath=CONFIG_FILE):
    """Enregistre le modèle sélectionné dans config.properties."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_path = os.path.join(script_dir, filepath) if not os.path.isabs(filepath) else filepath
    lines = []
    found = False
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in line:
                k, _ = line.split("=", 1)
                if k.strip() == "model_id":
                    lines[i] = f"model_id={model_name}\n"
                    found = True
                    break
    if not found:
        lines.append(f"model_id={model_name}\n")
    with open(target_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


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
    """Affiche une boîte de dialogue modale pour confirmer la suppression avec choix par flèches ou touches directes."""
    h, w = stdscr.getmaxyx()
    box_h = 11
    box_w = min(66, w - 4)
    start_y = max(0, (h - box_h) // 2)
    start_x = max(0, (w - box_w) // 2)

    win = curses.newwin(box_h, box_w, start_y, start_x)
    win.keypad(True)

    curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_RED)     # Bouton Oui sélectionné / Alerte
    curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_CYAN)    # Bouton Non sélectionné
    curses.init_pair(12, curses.COLOR_RED, -1)                     # Bouton Oui non sélectionné

    # 0 = Oui (supprimer), 1 = Non (annuler)
    selected_btn = 0

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

        size_str = f"Espace disque libéré : {model_size}"
        win.addstr(5, max(2, (box_w - len(size_str)) // 2), size_str, curses.A_DIM)

        # Affichage interactif des deux boutons
        btn_oui = " [ Oui (supprimer) ] "
        btn_non = " [ Non (annuler) ] "
        spacing = 4
        total_btn_len = len(btn_oui) + spacing + len(btn_non)
        btn_start_x = max(2, (box_w - total_btn_len) // 2)

        oui_attr = (curses.color_pair(10) | curses.A_BOLD) if (selected_btn == 0) else (curses.color_pair(12) | curses.A_NORMAL)
        non_attr = (curses.color_pair(11) | curses.A_BOLD) if (selected_btn == 1) else curses.A_NORMAL

        win.addstr(7, btn_start_x, btn_oui, oui_attr)
        win.addstr(7, btn_start_x + len(btn_oui) + spacing, btn_non, non_attr)

        hint = "Naviguez avec [← / →] puis [Entrée], ou tapez 'o' / 'n'"
        win.addstr(9, max(2, (box_w - len(hint)) // 2), hint, curses.A_DIM)

        win.refresh()
        key = win.getch()

        # Confirmation directe par 'o', 'O', 'y', 'Y'
        if key in (ord("o"), ord("O"), ord("y"), ord("Y")):
            return True
        # Annulation directe par 'n', 'N', 'q', 'Q', Échap
        elif key in (ord("n"), ord("N"), ord("q"), ord("Q"), 27):
            return False
        # Navigation entre Oui et Non par flèches ou Tab
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN, ord("\t"), ord("h"), ord("l")):
            selected_btn = 1 - selected_btn
        # Validation par touche Entrée
        elif key in (10, 13, curses.KEY_ENTER):
            return (selected_btn == 0)


def is_active_model(model_name, active_name):
    """Vérifie si le modèle correspond au modèle configuré (avec ou sans :latest)."""
    if not active_name:
        return False
    if model_name == active_name:
        return True
    if model_name.split(":")[0] == active_name:
        return True
    if active_name.split(":")[0] == model_name:
        return True
    return False


def main_tui(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    curses.use_default_colors()

    # Paires de couleurs
    curses.init_pair(1, curses.COLOR_CYAN, -1)     # Titre
    curses.init_pair(2, curses.COLOR_GREEN, -1)    # Succès / en ligne
    curses.init_pair(3, curses.COLOR_RED, -1)      # Erreur / hors ligne
    curses.init_pair(4, curses.COLOR_YELLOW, -1)   # Attention
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Sélection curseur
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)  # En-tête de tableau
    curses.init_pair(7, curses.COLOR_GREEN, -1)    # Modèle actif

    selected_idx = 0
    message = ""
    message_type = "info"

    models, status, err = get_models()
    active_model = get_active_model_from_props()

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
            status_text = "● Serveur actif"
            stdscr.addstr(1, max(35, w - len(status_text) - 4), status_text, curses.color_pair(2) | curses.A_BOLD)
        elif status == "cli_fallback":
            status_text = "● Mode CLI (API hors ligne)"
            stdscr.addstr(1, max(35, w - len(status_text) - 4), status_text, curses.color_pair(4) | curses.A_BOLD)
        else:
            status_text = "● Serveur hors ligne"
            stdscr.addstr(1, max(35, w - len(status_text) - 4), status_text, curses.color_pair(3) | curses.A_BOLD)

        stdscr.addstr(2, 2, "─" * (w - 4), curses.A_DIM)

        # 2. Statistiques et modèle configuré
        nb_models = len(models)
        info_str = f"Modèles : {nb_models} | Actif pour l'agent (config.properties) : [{active_model}]"
        stdscr.addstr(3, 2, info_str[:w - 4], curses.A_BOLD)

        # Message temporaire s'il existe
        if message:
            msg_color = curses.color_pair(2) if message_type == "success" else curses.color_pair(3)
            max_msg_len = w - 4
            stdscr.addstr(4, 2, message[:max_msg_len], msg_color | curses.A_BOLD)
        else:
            stdscr.addstr(4, 2, "Astuce : Appuyez sur [Entrée] ou [s] pour choisir le modèle actif de l'agent.", curses.A_DIM)

        # 3. En-têtes du tableau
        header_y = 6
        col_name_w = max(24, w - 50)
        table_header = f" {'#':<3} {'NOM DU MODÈLE':<{col_name_w}} {'TAILLE':<10} {'PARAMS':<8} {'STATUT':<8} "
        table_header_padded = table_header.ljust(w - 4)
        stdscr.addstr(header_y, 2, table_header_padded[:w - 4], curses.color_pair(6) | curses.A_BOLD)

        # 4. Liste des modèles
        list_y_start = 7
        visible_rows = h - list_y_start - 3

        if not models:
            if status == "offline":
                stdscr.addstr(list_y_start + 2, 4, "Impossible de joindre Ollama.", curses.color_pair(3))
                stdscr.addstr(list_y_start + 3, 4, "Vérifiez que le serveur est démarré avec './setup_wsl.sh'.", curses.A_DIM)
            else:
                stdscr.addstr(list_y_start + 2, 4, "Aucun modèle local trouvé.", curses.color_pair(4))
                stdscr.addstr(list_y_start + 3, 4, f"Téléchargez un modèle avec 'ollama pull {active_model}'.", curses.A_DIM)
        else:
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
                is_active = is_active_model(m["name"], active_model)

                status_label = "★ ACTIF" if is_active else ""
                row_str = f" {model_idx + 1:<3} {m['name']:<{col_name_w}} {m['size']:<10} {m['params']:<8} {status_label:<8} "
                row_str_padded = row_str.ljust(w - 4)

                if is_selected:
                    stdscr.addstr(curr_y, 2, row_str_padded[:w - 4], curses.color_pair(5) | curses.A_BOLD)
                elif is_active:
                    stdscr.addstr(curr_y, 2, row_str_padded[:w - 4], curses.color_pair(7) | curses.A_BOLD)
                else:
                    attr = curses.A_NORMAL if (i % 2 == 0) else curses.A_DIM
                    stdscr.addstr(curr_y, 2, row_str_padded[:w - 4], attr)

        # 5. Barre de navigation et raccourcis en bas
        footer_y = h - 2
        stdscr.addstr(footer_y - 1, 2, "─" * (w - 4), curses.A_DIM)
        shortcuts = " [↑/↓] Naviguer  [Entrée/s] Choisir pour l'agent  [d] Supprimer  [r] Actualiser  [q] Quitter"
        stdscr.addstr(footer_y, 2, shortcuts[:w - 4], curses.color_pair(1))

        stdscr.refresh()

        key = stdscr.getch()

        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (curses.KEY_UP, ord("k"), ord("K")):
            if nb_models > 0:
                selected_idx = (selected_idx - 1) % nb_models
        elif key in (curses.KEY_DOWN, ord("j"), ord("J")):
            if nb_models > 0:
                selected_idx = (selected_idx + 1) % nb_models
        elif key in (ord("s"), ord("S"), 10, 13):
            # Sélectionner le modèle pour config.properties
            if nb_models > 0 and selected_idx < nb_models:
                chosen_name = models[selected_idx]["name"]
                set_active_model_in_props(chosen_name)
                active_model = chosen_name
                message = f"✔ Modèle '{chosen_name}' défini comme modèle actif dans config.properties !"
                message_type = "success"
        elif key in (ord("r"), ord("R")):
            message = "Actualisation..."
            message_type = "info"
            models, status, err = get_models()
            active_model = get_active_model_from_props()
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
                        active_model = get_active_model_from_props()
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
