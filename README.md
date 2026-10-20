# Uncharted 3 RPCS3 Mouse Driver

Raw mouse aiming for **Uncharted 3: Drake's Deception** (update 1.19) on **RPCS3**. It replaces the emulated right stick with direct mouse input: no deadzone, no acceleration, no smoothing, and the same sensitivity at any frame rate.

## Install

1. Download `UC3MouseAim.exe` from [Releases](../../releases) and put it next to `rpcs3.exe`.
2. Run it. It adds the **UC3 Mouse Aim** patch to `patches/imported_patch.yml` and enables it.
3. In RPCS3, open **Pads** and, with the Keyboard handler, map **R1** to `Mouse Left` and **L1** to `Mouse Right`. Leave the right stick unmapped.
4. Start the game. If it was already running, restart it, because patches load only at boot.
5. In the program, choose **3) Start mouse aim** and keep its window open.

Supported versions: BCES01175/01176/01670/01692, BCUS98233/99086, BCJS37004, BCAS25009/25014, NPEA00422, NPUA80858, all on update 1.19.

## Settings

| Setting | Meaning |
|---|---|
| Sensitivity | Camera turn per hand movement. `1.0` is 28.6 cm/360°. |
| DPI | Your mouse's DPI. |
| Free-look / ADS multiplier | Extra scale without aiming / with right mouse held. |
| Invert Y, hide cursor | As named. |

**Why separate DPI?** Sensitivity is set per centimetre of hand movement, not per sensor count. Enter your real DPI and the same sensitivity gives the same cm/360 at 400 or 3200 DPI; a higher DPI only gives finer steps.

Both axes and both modes are already equalised: one count turns the camera by the same angle. The settings page shows the result in cm/360.

## Troubleshooting

| Status | Fix |
|---|---|
| `running WITHOUT the patch` | Restart the game. Check that *UC3 Mouse Aim* is ticked in *Manage → Game Patches*. |
| `A different mouse patch is active` | Disable other mouse/aim patches for UC3, then restart the game. |
| `memory cannot be accessed` | RPCS3 runs as administrator. Run this program as administrator too. |
| `paused` | Click into the game window. |

## How it works

**Patch** (90 writes to the 1.19 executable):
- Removes the stick deadzone, response curve, direction-reversal filter and magnitude clamp.
- Removes aim acceleration, aim assist and slowdown.
- Removes the free-look turn ramp, axis snapping and camera spring.
- Hooks gamepad polling (`0x00894210`) with a routine at `0x00DA0460`. Every frame it reads the mouse total from `0x0144FF00`, takes the change since the last frame, and divides it by the game's frame time. The game then multiplies by the same frame time, so **rotation = counts × scale** at any FPS.

**Program:**
- Reads Windows Raw Input (unaccelerated sensor counts) and adds each event to a running total in game memory (RPCS3 base `0x300000000`). A running total cannot drop or double movement between frames.
- Right mouse button switches to the ADS multiplier.
- Patch status comes from the instruction at the hook address:
  - original instruction: the game booted without the patch;
  - branch to the counter routine: the patch is active;
  - anything else: another patch changed this code.
- Input is sent only while the game window has focus. Then the cursor is hidden and clipped to the window's centre.

## Build

```bat
pip install pyinstaller
build.bat
```

The build writes `dist\UC3MouseAim.exe`. To run without building, use `python uc3_mouse_aim.py` (Python 3.9+, no dependencies).

`patch/UC3-Mouse-Aim.yml` is the same patch, for importing by hand in *Manage → Game Patches*.

Fan project, not affiliated with Naughty Dog, Sony or RPCS3.
