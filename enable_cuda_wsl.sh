#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  Configuration & Diagnostic CUDA / GPU NVIDIA pour WSL2  "
echo "=========================================================="

echo ""
echo "[1/4] Vérification de l'environnement WSL2..."
if [ ! -e "/dev/dxg" ]; then
    echo "❌ Le composant /dev/dxg est absent."
    echo "Cela signifie que le pont GPU entre Windows et WSL n'est pas actif."
    echo ""
    echo "Actions requises côté Windows :"
    echo "  1. Ouvrez PowerShell en tant qu'administrateur et lancez :"
    echo "       wsl --update"
    echo "       wsl --shutdown"
    echo "  2. Assurez-vous d'avoir installé les pilotes NVIDIA GeForce / Studio récents sous Windows :"
    echo "       https://www.nvidia.com/Download/index.aspx"
    echo "  3. Relancez votre terminal WSL."
    exit 1
else
    echo "✔ Pont GPU WSL2 (/dev/dxg) présent."
fi

echo ""
echo "[2/4] Configuration des chemins de bibliothèques CUDA (/usr/lib/wsl/lib)..."
if [ -d "/usr/lib/wsl/lib" ]; then
    echo "✔ Dossier /usr/lib/wsl/lib trouvé."

    # Vérification de libcuda.so.1
    if [ -f "/usr/lib/wsl/lib/libcuda.so.1" ]; then
        echo "✔ Bibliothèque CUDA détectée : /usr/lib/wsl/lib/libcuda.so.1"
        if [ ! -e "/usr/lib/wsl/lib/libcuda.so" ]; then
            sudo ln -sf /usr/lib/wsl/lib/libcuda.so.1 /usr/lib/wsl/lib/libcuda.so 2>/dev/null || true
        fi
    fi

    # Configuration de la commande nvidia-smi
    if [ -f "/usr/lib/wsl/lib/nvidia-smi" ]; then
        echo "Création du lien /usr/local/bin/nvidia-smi depuis /usr/lib/wsl/lib..."
        sudo ln -sf /usr/lib/wsl/lib/nvidia-smi /usr/local/bin/nvidia-smi
    elif command -v nvidia-smi.exe &> /dev/null; then
        echo "Création du wrapper /usr/local/bin/nvidia-smi vers nvidia-smi.exe..."
        sudo tee /usr/local/bin/nvidia-smi > /dev/null << 'EOF'
#!/bin/sh
exec nvidia-smi.exe "$@"
EOF
        sudo chmod +x /usr/local/bin/nvidia-smi
    elif [ -f "/mnt/c/Windows/System32/nvidia-smi.exe" ]; then
        echo "Création du wrapper /usr/local/bin/nvidia-smi vers /mnt/c/Windows/System32/nvidia-smi.exe..."
        sudo tee /usr/local/bin/nvidia-smi > /dev/null << 'EOF'
#!/bin/sh
exec /mnt/c/Windows/System32/nvidia-smi.exe "$@"
EOF
        sudo chmod +x /usr/local/bin/nvidia-smi
    fi

    # Ajout au chargeur de bibliothèques dynamiques ldconfig
    echo "Configuration de /etc/ld.so.conf.d/ld.wsl.conf..."
    echo "/usr/lib/wsl/lib" | sudo tee /etc/ld.so.conf.d/ld.wsl.conf > /dev/null
    sudo ldconfig

    # Ajout au PATH dans ~/.bashrc si absent
    if ! grep -q "/usr/lib/wsl/lib" ~/.bashrc 2>/dev/null; then
        echo 'export PATH="$PATH:/usr/lib/wsl/lib"' >> ~/.bashrc
        echo "✔ Ajout de /usr/lib/wsl/lib dans ~/.bashrc."
    fi
else
    echo "❌ Le dossier /usr/lib/wsl/lib est introuvable."
    echo "Vérifiez que votre pilote NVIDIA est bien installé sur Windows et relancez WSL (wsl --shutdown)."
    exit 1
fi

echo ""
echo "[3/4] Vérification de conflits de pilotes Linux..."
if dpkg -l | grep -E "nvidia-driver-[0-9]+" &> /dev/null; then
    echo "⚠ Attention : un pilote d'affichage Linux (nvidia-driver-xxx) a été détecté dans WSL."
    echo "  Rappel : Sous WSL2, les pilotes graphiques ne doivent JAMAIS être installés via apt !"
    echo "  Seul le pilote hôte Windows doit être installé."
    echo "  Pour le nettoyer si vous rencontrez des problèmes :"
    echo "    sudo apt-get purge -y '*nvidia-driver*' && sudo apt-get autoremove -y"
else
    echo "✔ Aucun conflit de pilote graphique Linux détecté."
fi

echo ""
echo "[4/4] Test et affichage des caractéristiques du GPU..."
export PATH="$PATH:/usr/lib/wsl/lib"

GPU_CMD=""
if command -v nvidia-smi &> /dev/null; then
    GPU_CMD="nvidia-smi"
elif command -v nvidia-smi.exe &> /dev/null; then
    GPU_CMD="nvidia-smi.exe"
elif [ -f "/mnt/c/Windows/System32/nvidia-smi.exe" ]; then
    GPU_CMD="/mnt/c/Windows/System32/nvidia-smi.exe"
fi

if [ -n "$GPU_CMD" ]; then
    echo "✔ Succès ! GPU NVIDIA opérationnel dans WSL2 :"
    echo "----------------------------------------------------------"
    GPU_INFO=$($GPU_CMD --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true)
    if [ -n "$GPU_INFO" ]; then
        while IFS=',' read -r GPU_NAME GPU_VRAM; do
            GPU_NAME_CLEAN="$(echo "${GPU_NAME:-}" | xargs)"
            GPU_VRAM_CLEAN="$(echo "${GPU_VRAM:-}" | xargs)"
            echo "   • Carte vidéo : $GPU_NAME_CLEAN"
            echo "   • VRAM totale : $GPU_VRAM_CLEAN"
        done <<< "$GPU_INFO"
    else
        $GPU_CMD
    fi
    echo "----------------------------------------------------------"
    echo "Ollama détectera désormais automatiquement votre GPU CUDA !"
else
    echo "❌ Impossible d'exécuter nvidia-smi ou nvidia-smi.exe."
fi
