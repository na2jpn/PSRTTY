# Z-Link source review for PSRTTY 1.14

Reviewed 2026-10-10:

- zLog commit `6e309daf062d599b7c324c1210d2756f6f32bcfe` (2026-10-01).
  https://github.com/jr8ppg/zLog/tree/6e309daf062d599b7c324c1210d2756f6f32bcfe
- zServer commit `cd48d5d2d67651d367603ff863b0804a78b954ae` (2026-09-27).
  https://github.com/jr8ppg/zServer/tree/cd48d5d2d67651d367603ff863b0804a78b954ae

`zlog/UZLinkForm.pas`: SendQSO sends #ZLOG# PUTQSO plus QSOinText; WriteData appends line break. CommProcess decodes PUTQSO, checks QSO ID, calls MyContest.LogQSO and refreshes the grid. Its command truncation limits the body to 255 characters. Our CP932-byte limit is conservative.
`zlog/UzLogQSO.pas`: QSOinText/TextToQSO define 31 tilde-separated fields with Delphi quoting. Time is Delphi TDateTime (1899-12-30 epoch), Freq is kHz text, reserve3 is QSO ID. CheckQSOID uses ID div 100 (last two digits are edit count).
`zlog/UzlogConst.pas`: RTTY=4; stable band indexes 0..15 for 160m..3cm. MAX_TX=16.
`zlog/UzLogGlobal.pas`: NewQSOID uses TX*100000000+serial*10000+random*100. PSRTTY uses the same shape and checks server IDs before a first send.
`UCliForm.pas`: Process_PutQso posts record addition to the server GUI. The command loop relays PUTQSO to all clients except its sender. GETQSOIDS ends with ENDQSOIDS; GETLOGQSOID returns PUTLOGEX followed by RENEW. Normal TCP has no authentication; secure mode uses a separate TLS/login path not implemented in PSRTTY 1.14.
`UServerForm.pas`: OnPutQSO checks IDs before adding to MasterLog.

No upstream source is bundled or changed. The client is independently implemented from the wire format. TCP tests use a small protocol simulator, not a running Windows zLog or zServer binary. Tests verify socket framing, persistence, registration/readback and disconnection recovery. Windows application interoperability remains to be verified.
