2026-10-08  Ver1.09
・Added FT-817/FT-817ND, FT-818ND and FT-857/FT-857D to Hamlib selection, with CAT/audio guidance for radios without direct USB.
・Added older ICOM radios with CI-V frequency reading/control. Distinguishes direct USB, external CI-V/audio and radios also requiring external PTT.
・Added radio PTT as an external-interface role while preserving existing pre-key profiles.
・Added Direct TX: up to two lines, a correction delay, TX while typing, sent-text colors, replay and clear/stop.
・Manual TX now has Direct, Clear and 1TX. During transmission 1TX changes to STOP.
・Ctrl+F12 / Shift+F12 toggle Direct TX. F11/F12 focus it or control TX/STOP and replay according to the active window.
・Added a modeless keyboard shortcut guide below Initial setup guide.
・MARK/LTRS/NUL idle no longer splits received lines. A newline or sustained signal loss finalizes the line. TX starts with LTRS.
・Updated Japanese/English guidance and contact records while retaining settings, profiles and ADIF logs.
・Made Direct TX, Cross scope, Control, Sub decode and the keyboard shortcut guide independent windows. Selecting the main window can bring it in front while TX, reception and display updates continue. Open/recall controls bring the utility window forward.
- Main RX and Audio IN share five level colors and matching labels: gray shows no text, light blue Low, green Good (30–79%), yellow High (80–89%) and red Over! (90% or more). Display smoothing and band confirmation reduce flicker without changing audio input or decoding. The Waveform height and input level section of the initial setup guide also explains RX colors and input-level adjustment.


## Direct TX
TX while typing defaults ON. Each character has a 0.5-second correction delay; uncommitted IME composition is not transmitted. Up to two lines. Waiting for input sends continuous MARK while retaining PTT. Pending text is RGB(136,153,175); sent text is black. Colors indicate local audio output progress, not peer reception. Committed text cannot be edited during TX. F12 restarts from the beginning after the current character. Newlines send CR/LF while retaining PTT. With typing TX OFF, the button sends both lines then stops. STOP retains the text and prevents automatic pending output; F11 resumes its unsent tail and F12 replays all. Clear stops and removes text. Closing stops TX.

## RX idle
CR/LF finalizes a line. Valid MARK or RTTY frames, including LTRS/NUL, retain it during typing pauses. A 1.5-second signal loss finalizes it. The short-text filter applies to finalized lines. Check fading, noise and nearby carriers with real audio.

## Connections
ICOM always uses CI-V. Blue notices identify external-PTT radios: select separate CI-V and PTT COM ports, enable External interface with Radio PTT control role, and select External interface as the Radio tab PTT method. Existing pre-key profiles are retained. Radios without USB need separate audio wiring. Older models default to manual mode setup; set LSB/USB and audio input on the radio. IC-735/820H/821H use four-byte frequency messages. External-PTT radios cannot report TX through CI-V; controls are guarded using PSRTTY's external PTT state, not physical radio PTT.
Select the actual FT-817/818/857 model, or manually choose FT-857 as a fallback. No automatic substitution. CAT uses 8N2 and no handshake. Hamlib remains 4.7.2. Unsupported controls remain on the radio. SCU-17 uses Enhanced COM for CAT and its audio devices for audio; use Standard COM PTT/CW/FSK according to the interface wiring.
