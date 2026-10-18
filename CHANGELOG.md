# Changelog

## 1.0.2

- HD haptics work again: output report 0x32 is 142 bytes (report id + 141), as
  the controller's HID descriptor says. The CRC sat one byte early, so the
  DualSense dropped every haptics packet. Packets are now byte-identical to
  SAxense's.

## 1.0.1

- Mouse mode: R2 = left click, R1 = right click.
- Sticks no longer drive the mouse by default; choose "nothing", "right stick
  scrolls" or "left moves, right scrolls" on the Mouse page.
- Light bar: picking a colour shows it on the pad right away, mouse mode keeps
  your colour unless you pick a separate one, and a hint explains when it doesn't.
- The controller picture no longer tilts with the accelerometer.
- The app icon shows in the task manager (absolute icon path, Plasma cache refresh).

## 1.0.0

First public release.

- Share gestures: touchpad mouse, window switcher, minimise and force-close
  with an on-screen hold ring, quick-launch wheel, Steam keyboard, volume,
  monitor / TV switching.
- Remappable Share + button shortcuts (20+ actions).
- Control center (Qt Quick) with gamepad navigation, settings search, tray
  icon, live DualSense picture, English and Russian.
- Light bar modes (solid, breathe, rainbow, battery), action flashes,
  mouse-mode colour, player and mic LEDs.
- On-screen toasts above fullscreen games (wlr-layer-shell overlay).
- Rumble or experimental HD haptics over Bluetooth.
- Idle power-off, low-battery warnings, config hot reload.
- User-level installer, no root needed.
