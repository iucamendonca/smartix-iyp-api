#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
UNIT="$HOME/.config/systemd/user"
mkdir -p "$UNIT"
cat > "$UNIT/smartix-iyp-update.service" <<EOF
[Unit]
Description=Atualizar banco Internet Yellow Pages do SmartIX

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=/usr/bin/env bash $ROOT/scripts/atualizar.sh
EOF
cat > "$UNIT/smartix-iyp-update.timer" <<'EOF'
[Unit]
Description=Verificação diária de novos dumps do IYP

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true
Unit=smartix-iyp-update.service

[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now smartix-iyp-update.timer
systemctl --user list-timers --all smartix-iyp-update.timer
printf '\nAtenção: um timer de usuário pode depender da sessão ativa; para execução após logout no servidor, configure linger/systemd de sistema com o administrador.\n'
