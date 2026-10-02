# PSRTTY 1.07 implementation review

Release date: 2026-10-03. Source review performed 2026-10-02.

## HAMLOG

- Target Turbo HAMLOG/Win **5.48**, as listed on https://hamlog.xii.jp/ .
- Protocol: official `HamlogMs.txt`, **5.27c and later**, from https://hamlog.xii.jp/mou/soft/Th527api.zip .
- MMTTY reference: https://github.com/n5ac/mmtty , commit `5a21f1db8fb5b53486cfa66d6bf0a953a2ae762c`, `Loglink.cpp`. The legacy MMTTY field layout is not copied: this implementation uses the current documented 1–14 field commands.
- Native target class `TThwin`, WM_COPYDATA 0x004A; CP932 strings with terminating NUL and byte lengths. COPYDATASTRUCT dwData uses pointer width. Win32 function signatures are explicitly declared for 32/64-bit Windows.
- Replies go to a temporary hidden window owned by the worker thread. `THW_APPLIHWND` requests the main HAMLOG HWND as reply sender; only that sender is accepted. SendMessageTimeout permits reentrant replies and uses a 2-second bound for each native call.
- Mutating requests include THW_SHUUSEI_WIN, the documented confirmation flag for an existing-record edit window. An unanswered confirmation times out and prevents subsequent automatic save.
- Read input through command 115 (leading empty line, then 14 fields). Write CALL/date/JST time/RST-S/RST-R/frequency/mode/Remarks1/Remarks2 with commands 1–7/13/14. CALL lookup uses command 1 with THW_ENTER, then reads Name/QTH.
- Read back CALL, date, time, frequency, both RSTs, mode and remarks before issuing save. Save uses command 18 with THW_SAVEBOX_OFF. The API return is an input-window handle, **not a durable database receipt**. UI therefore says “Save requested”; a still-filled CALL after save produces an uncertain-result error.
- A journal in `var/hamlog-transfer.jsonl` is flushed before the first transfer mutation. Interrupted/completed attempts with the same QSO fingerprint are never automatically repeated. This journal is user runtime data, not part of an updater payload.
- Existing input is protected, including a same-CALL draft. Only an unchanged draft created by this PSRTTY session’s explicit lookup may be filled automatically. No clear-input command is sent. Code/GL/QSL/Name/QTH remain owned by HAMLOG.
- Local ADIF is committed first; both manual and TU73 auto logging share the same hook. Transfer failure cannot remove the local QSO. HAMLOG I/O runs outside the GUI thread; application close waits for the outstanding operation.
- No database DLL calls, direct HDB writes, keystroke automation, reverse synchronization, or automatic retries of uncertain saves.

## zLog

- Release: **3.0.4.0**, tag **ZLOG3040**, commit `6e309daf062d599b7c324c1210d2756f6f32bcfe`.
- Source: https://github.com/jr8ppg/zLog/tree/ZLOG3040 .
- Reviewed `zlog/UzLogQSO.pas`, `TLog.LoadFromFileAsAdif`, and `zlog/UzLogContest.pas`, `ADIF_ExchangeRX_FieldName`.
- The importer reads QSO_DATE/TIME_ON in UTC (minute precision), maps to contest time settings, and reads RST_SENT/RST_RCVD, MODE, BAND, FREQ and COMMENT.
- Sent exchange: STX_STRING for no-serial contests; numeric STX otherwise. Receive exchange: SRX_STRING or SRX unless the contest provides a specific field.
- JARL WW RTTY reads AGE; CQ WW reads CQZ. Standard ADIF alone is therefore insufficient for those contest-specific receive exchanges.
- PSRTTY adds AGE or CQZ as appropriate. Compound `05 MA` remains in SRX_STRING and COMMENT; CQZ is numeric `5`, STATE is `MA`. **zLog's reviewed importer does not read STATE**, so its received exchange/multiplier needs manual reconciliation for those contacts. No nonstandard compound value is inserted into CQZ.
- COMMENT also retains both raw exchanges (including leading zeroes) and own CALL. zLog does not set the station CALL from STATION_CALLSIGN in this importer; users choose the correct station/contest first.
- The included three sample ADIFs are synthetic. They cover leading zeroes, distinct RST-S/RST-R, CQWW zone+state and the JST midnight boundary. They belong in a disposable test log, never a real submission.

## Hamlib

Reviewed the bundled **4.7.2** source archive, matching the bundled DLL baseline.

| Models | NB/NR | Receive width |
|---|---|---|
| FT-991/FT-991A, FTX-1 | get/set with readback | Per-mode Yaesu tables, including corrected FTX-1 SSB 2250/2450 Hz choices |
| FT-710, FTDX10, FTDX101D/MP, FTDX3000 | get/set with readback | Per-mode Yaesu tables |
| TS-590SG | get/set with readback | DATA/SSB: read SLOPE_HIGH and SLOPE_LOW, set high cut to requested width + current low cut; reject if low cut changed since selection |
| TS-890S, TS-990S | get/set with readback | Not implemented by this Hamlib version; no false success or nominal width shown |

- `rigs/yaesu/newcat.c`: `newcat_set_rx_bandwidth` and matching get tables. Choices differ across FT-991, FTDX3000, recent desktop models and FTX-1.
- `rigs/kenwood/ts590.c`: slope capability masks and cutoff tables. `set_mode` sets SH, but its get_mode width may be SH or SH−SL depending on mode. Using both supported level calls avoids that mismatch.
- `rigs/kenwood/ts890s.c`, `ts990s.c`, `kenwood.c`: NB/NR supported; generic set_mode does not implement bandwidth for these two models and neither advertises the slope-level controls. Their advertised nominal filters do not prove bandwidth control exists.
- Operations require a connected controller, a known state, RX rather than TX, and successful readback. The model allowlist that previously restricted NB/NR to two Yaesu models is removed.

## Verification boundary

The reviewed source and protocol mock tests are the basis for the target-version labels. No radio hardware, Windows HAMLOG process, or zLog GUI was available in the Linux test environment. The Windows build and actual device/application interoperability have not been executed here. These are not claimed as hardware-tested features.
