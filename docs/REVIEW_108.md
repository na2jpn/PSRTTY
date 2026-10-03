# Ver1.08 source review

IC-7760 official CI-V reference: https://www.icomjapan.com/support/manual/4227/
Reviewed IC-7760_ENG_CI-V_2.pdf (not redistributed).
Default address B2; frequency 03/05; mode 04/06; DATA 1A 06 (00–03); MAIN/SUB mode/DATA/filter 26 00/01; PTT 1C 00; tuner 1C 01; ALC 15 13; NB/NR/AN/MN 16 22/40/41/48. Shared CI-V transport is retained; IC-7760 selected-side filter read uses 04 and 1A 06 and writes 1A 06 (DATA1–3) or 06 (DATA OFF), since 26 00 specifically addresses MAIN. DATA OFF writes filter byte 00 per the guide. DATA1 input must be configured on the radio.

Secondary audio uses its own callback stream and the unscaled TX waveform; it never writes synchronously from the main stream's block loop. Gain is independent of the main TX gain, finite and clamped to 0–2, with samples clipped to [-1,1]. It has no PTT callbacks. Missing, duplicate or failed output produces a status notice; primary TX success still depends on the primary stream and PTT. Stream cleanup follows PTT release. Clock differences between separate devices can introduce a small monitoring offset.

Windows identity is set before QApplication, using a version-independent application ID. ICO contains 16,24,32,48,64,128,256 pixel sizes and is bundled for runtime and EXE embedding. Existing pinned shortcuts may need unpin/re-pin. Windows taskbar and hardware have not been exercised on this Linux host.

The 1.07 runtime PNG failed actual QIcon.pixmap decoding (libpng Read Error; all sizes null). The existing ICO decodes successfully at every size. Runtime and About now use that ICO; regression checks decode every size, rather than only checking QIcon.isNull.
