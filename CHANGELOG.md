# Changelog

## Unreleased

- Charging is visible everywhere: the sidebar card says "Charging" with a
  pulsing bolt and a light sweep on the bar, the battery chip breathes, the
  tray icon gets a white bolt and its tooltip says "charging".
- Tray icon: the controller glyph now fills the slot like other tray icons
  (no dark tile), with the battery bar under it.
- Toasts when the cable goes in and when the pad is full; the battery is
  checked every 5 s instead of 30.
- Tray menu: "Turn the pad off" and an "Auto power off" submenu
  (never / 10 / 15 / 30 / 60 min); the same setting lives in System.
- Bolt glyphs are Phosphor icons instead of an emoji.

## 1.0.3

- Quick-launch wheel: aim with either stick, launch with ✕, L3 or R3.
  Releasing R1 no longer launches, so the wheel never fires by accident.
- Wheel launch confirmation: the picked sector flashes, a contour ripples out,
  a check mark draws itself in the centre, then the wheel fades away.
- HD haptics: clicks no longer go missing after a pause (keepalive + warm-up on
  Share), Try it reacts on press, cues are distinct, strength goes up to 300 %.
- Window switcher: if KWin closes it by itself (e.g. a touchpad tap), Alt is
  released within a second instead of sticking.
- App menu icon: PNG icons, Plasma's menu showed "?" for the SVG path.

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
