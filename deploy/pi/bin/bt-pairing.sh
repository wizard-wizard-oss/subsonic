#!/usr/bin/env bash
# Mode appairage Bluetooth pendant 2 minutes. Les appareils appairés sont
# ensuite "de confiance" et se reconnectent tout seuls.
bluetoothctl power on >/dev/null
bluetoothctl pairable on >/dev/null
bluetoothctl discoverable on >/dev/null
for _ in $(seq 1 60); do
  for mac in $(bluetoothctl devices Paired 2>/dev/null | awk '{print $2}'); do
    bluetoothctl trust "$mac" >/dev/null 2>&1
  done
  sleep 2
done
bluetoothctl discoverable off >/dev/null
bluetoothctl pairable off >/dev/null
