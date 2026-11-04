#!/usr/bin/env bash
# Choisit la sortie audio par défaut : USB (ampli en USB) sinon HDMI.
# Pour forcer une sortie précise, mettre son nom (pactl list short sinks)
# dans ~/.local/share/pi-media/hdmi-sink
OVERRIDE="$HOME/.local/share/pi-media/hdmi-sink"
sink=""
for _ in $(seq 1 30); do
  if [ -s "$OVERRIDE" ]; then
    sink="$(head -n1 "$OVERRIDE")"
  else
    all="$(pactl list short sinks 2>/dev/null | awk '{print $2}' || true)"
    sink="$(echo "$all" | grep -i usb | sort | head -n1 || true)"
    [ -n "$sink" ] || sink="$(echo "$all" | grep -i hdmi | sort | head -n1 || true)"
  fi
  [ -n "$sink" ] && break
  sleep 1
done
[ -n "$sink" ] || exit 0
pactl set-default-sink "$sink"
pactl set-sink-volume "$sink" 100%
