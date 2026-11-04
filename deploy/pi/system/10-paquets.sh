#!/usr/bin/env bash
# Paquets système : son, AirPlay, Bluetooth, menu (Tk, numpy pour l'égaliseur), lecture (mpv), textes (YAML).
set -euo pipefail
. "$(dirname "$0")/common.sh"
say "Paquets système"
sudo apt-get update
sudo apt-get install -y shairport-sync avahi-daemon pulseaudio-utils pipewire-alsa python3-tk python3-numpy \
  python3-yaml curl mpv playerctl wtype bluez bluez-tools libspa-0.2-bluetooth
sudo usermod -aG input "$USER" || true          # lecture des touchers pour la veille
