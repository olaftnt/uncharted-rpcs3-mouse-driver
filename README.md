# Uncharted 3 RPCS3 Mouse Driver

Raw mouse aiming for **Uncharted 3: Drake's Deception** (update 1.19) on **RPCS3**. It replaces the emulated right stick with direct mouse input: no deadzone, no acceleration, no smoothing, and the same sensitivity at any frame rate.

## Install

1. Download `UC3MouseAim.exe` from [Releases](../../releases) and put it next to `rpcs3.exe`.
2. Stop all running RPCS3 processes.
3. Run `UC3MouseAim.exe`. It installs the **UC3 Mouse Aim** patch, enables it in the RPCS3 config, and shows *Ready - start RPCS3 and load the game*.
4. Start RPCS3 and load the game. Make sure the patch is enabled in **Manage → Game Patches**.
5. For keyboard controls, use RPCS3's normal keyboard-to-pad mapping.
6. In the program, choose **3) Start mouse aim** and keep its window open.

If the game is ever started without the patch, the program enables it again by itself. It then asks you to restart RPCS3.

Supported versions: BCES01175/01176/01670/01692, BCUS98233/99086, BCJS37004, BCAS25009/25014, NPEA00422, NPUA80858, all on update 1.19.

## Troubleshooting

| Status | Fix |
|---|---|
| `running WITHOUT the patch` | The patch has been re-enabled. Close RPCS3, start it again and load the game. |
| `memory cannot be accessed` | RPCS3 runs as administrator. Run this program as administrator too. |

## How it works

**Patch:**
- Removes the game's stick processing: deadzone, response curve, direction-reversal filter and magnitude clamp.
- Removes aim acceleration, aim assist and slowdown.
- Removes the free-look turn ramp, axis snapping and camera spring.
- Adds a routine to gamepad polling. Every frame it takes the mouse movement since the last frame and divides it by the game's frame time. The game then multiplies by the same frame time, so **rotation = counts × scale** at any FPS.

**Program:**
- Reads Windows Raw Input (unaccelerated sensor counts) and adds each event to a running total in game memory. A running total cannot drop or double movement between frames.
- The right mouse button switches to the ADS multiplier.
- Checks the game's code to tell whether the game was booted with the patch.
- Input is sent only while the game window has focus. Then the cursor is hidden and kept in the window's centre.

## Build

```bat
pip install pyinstaller
build.bat
```

To run without building, use `python uc3_mouse_aim.py` (Python 3.9+, no dependencies). The patch is also included as a YAML file in this repository, for importing by hand in *Manage → Game Patches*.

Fan project, not affiliated with Naughty Dog, Sony or RPCS3.
