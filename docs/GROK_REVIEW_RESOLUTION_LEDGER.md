# Grok review resolution ledger

Review snapshots: `/home/david/consolidation-20260906/reviews`. All review, comment and thread pages fetched; no pagination omitted. Status is provisional until code and tests are verified.

| PR | Finding | Severity | Current HEAD | Still valid? | Fix owner | Fix | Test | Status |
|---|---|---|---|---|---|---|---|---|
| agent-22 | tests use a fake transport. That is not Discord acknowledgement. | HIGH | `2986b2ceb7a386aee5637ab2880c256d2ecd9561` | Pending verification | Codex | — | — | OPEN |
| agent-22 | user Forum/thread origin is not this cutover path, and this PR does not fix it. | HIGH | `2986b2ceb7a386aee5637ab2880c256d2ecd9561` | Pending verification | Codex | — | — | OPEN |
| agent-22 | two-store migration is declared, not applied. | MEDIUM | `2986b2ceb7a386aee5637ab2880c256d2ecd9561` | Pending verification | Codex | — | — | OPEN |
| agent-22 | no Grok Bot canonical state API. | MEDIUM | `2986b2ceb7a386aee5637ab2880c256d2ecd9561` | Pending verification | Codex | — | — | OPEN |
| nave-42 | unknown→known coercion on evidence identity. | BLOCKER | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | future leakage through availability. | BLOCKER | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | `SETUP_FOUND` accepts only LATE/UNKNOWN evidence. | HIGH | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | missing `generated_at` becomes now. | HIGH | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | `as_of` is still retrieval time. | HIGH | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | non-finite payload values emit non-portable JSON. | MEDIUM | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | `FileResearchContext` does not apply `context_is_usable`. | MEDIUM | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | CLI `nave research status --workflow X --json` is not a `ResearchResult`. | MEDIUM | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | `_safe_name` collisions. | LOW | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-42 | `PointInTime` has no `observed_at` / `retrieved_at`. | LOW | `5f7b052b8599d0f751ef37159bbdc601b5e0c18c` | Pending verification | Codex | — | — | OPEN |
| nave-43 | unclassified transcript sentences become FACT. | HIGH | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | gold official series is dead. | HIGH | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | `evidence_quality` collapses PARTIAL into `TRANSCRIPT_ONLY`. | HIGH | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | `speaker_attributed: True` is hardcoded. | MEDIUM | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | FRED vintage / release time is not used. | MEDIUM | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | newest unprocessed video blocks older ones. | MEDIUM | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | cursor `last_processed_at` uses wall `datetime.now(UTC)` even when `now=` is injected. | MEDIUM | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | `nave intel context latest` dumps raw store JSON. | MEDIUM | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | RSS-unavailable path has no public-channel fallback | LOW | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-43 | keyword `tipo` / `bajo` will false-hit rates/down. | LOW | `dffc14b287b49e879cd81fa301a9696994df70c7` | Pending verification | Codex | — | — | OPEN |
| nave-44 | REPLAY result timestamps are LIVE wall clock. | BLOCKER | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-44 | unparseable `information_available_at` becomes `BEFORE_MOVE`. | BLOCKER | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-44 | LIVE `--cot-regime` override is silently discarded. | HIGH | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-44 | REPLAY loads current Cava context. | HIGH | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-44 | `_parse_time` naive/invalid → caller default. | HIGH | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-44 | funnel stage names overclaim. | MEDIUM | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-44 | `missed_moves` status is `ACTION_REQUIRED`. | MEDIUM | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-44 | `_asset_key` falls back to ticker. | MEDIUM | `f72efe403e88fd4ae79aaaa954794b1453202f17` | Pending verification | Codex | — | — | OPEN |
| nave-45 | usable Cava is encoded as `macro_regime="neutral"` and that licenses HOLD. | HIGH | `ad348f46e994d652d562b7bc0e39d376a4fbcb5a` | Pending verification | Codex | — | — | OPEN |
| nave-45 | previous-price persistence is not atomic with the result. | HIGH | `ad348f46e994d652d562b7bc0e39d376a4fbcb5a` | Pending verification | Codex | — | — | OPEN |
| nave-45 | CROSS with missing previous is `NO_SETUP`. | HIGH | `ad348f46e994d652d562b7bc0e39d376a4fbcb5a` | Pending verification | Codex | — | — | OPEN |
| nave-45 | `--refresh-ledger` mutates private ledger files. | MEDIUM | `ad348f46e994d652d562b7bc0e39d376a4fbcb5a` | Pending verification | Codex | — | — | OPEN |
| nave-45 | same ticker in multiple categories is allowed. | MEDIUM | `ad348f46e994d652d562b7bc0e39d376a4fbcb5a` | Pending verification | Codex | — | — | OPEN |
| nave-45 | CLI accepts a `stocks` key as the watch list. | MEDIUM | `ad348f46e994d652d562b7bc0e39d376a4fbcb5a` | Pending verification | Codex | — | — | OPEN |
| nave-45 | A2/A4 are not in the Quant adapter test. | LOW | `ad348f46e994d652d562b7bc0e39d376a4fbcb5a` | Pending verification | Codex | — | — | OPEN |
| nave-46 | House search is last-name only, then every PDF is labeled the requested subject. | HIGH | `f8b050a089879ebb3abf2b81319554764ef85412` | Pending verification | Codex | — | — | OPEN |
| nave-46 | official providers invent `owner="filer/household"` and `confidence=0.95`. | HIGH | `f8b050a089879ebb3abf2b81319554764ef85412` | Pending verification | Codex | — | — | OPEN |
| nave-46 | `SETUP_FOUND` is used for filing-level PDF receipts with `UNKNOWN` availability. | HIGH | `f8b050a089879ebb3abf2b81319554764ef85412` | Pending verification | Codex | — | — | OPEN |
| nave-46 | OGE `disclosure_date` is parsed as MM.DD.YYYY from the URL. | MEDIUM | `f8b050a089879ebb3abf2b81319554764ef85412` | Pending verification | Codex | — | — | OPEN |
| nave-46 | no amendment model. | MEDIUM | `f8b050a089879ebb3abf2b81319554764ef85412` | Pending verification | Codex | — | — | OPEN |
| nave-46 | `_stable_id` prefers raw `source_url` as the id. | MEDIUM | `f8b050a089879ebb3abf2b81319554764ef85412` | Pending verification | Codex | — | — | OPEN |
| nave-46 | FMP fallback is labeled secondary (good) but still normalized into the same SETUP_FOUND stream. | MEDIUM | `f8b050a089879ebb3abf2b81319554764ef85412` | Pending verification | Codex | — | — | OPEN |
| nave-47 | Dune cache freshness is optional. | HIGH | `200fc49b47cba1fb3c8d586f1312c79f3ffa112b` | Pending verification | Codex | — | — | OPEN |
| nave-47 | `ResearchResult` clocks are wall time. | HIGH | `200fc49b47cba1fb3c8d586f1312c79f3ffa112b` | Pending verification | Codex | — | — | OPEN |
| nave-47 | `nave memecoin dune materialize` does not call `resource_guard.check`. | HIGH | `200fc49b47cba1fb3c8d586f1312c79f3ffa112b` | Pending verification | Codex | — | — | OPEN |
| nave-47 | mixed-quality universes cannot be `SETUP_FOUND`. | MEDIUM | `200fc49b47cba1fb3c8d586f1312c79f3ffa112b` | Pending verification | Codex | — | — | OPEN |
| nave-47 | `narrative` is in `FEATURES` / thesis text and is never gated. | MEDIUM | `200fc49b47cba1fb3c8d586f1312c79f3ffa112b` | Pending verification | Codex | — | — | OPEN |
| nave-47 | `query_identity` hashes empty `query_text` when CLI omits it. | MEDIUM | `200fc49b47cba1fb3c8d586f1312c79f3ffa112b` | Pending verification | Codex | — | — | OPEN |
| nave-47 | missed-moves / evaluate still emit `ACTION_REQUIRED` / selected hits with `hit: value > 0` and no costs. | MEDIUM | `200fc49b47cba1fb3c8d586f1312c79f3ffa112b` | Pending verification | Codex | — | — | OPEN |
| nave-48 | `PROMISING` is granted without costs, identity, or finite returns. | HIGH | `ecc05bf0b74199daafc77b14c86bfa2597f2fb27` | Pending verification | Codex | — | — | OPEN |
| nave-48 | evaluation is not point-in-time. | HIGH | `ecc05bf0b74199daafc77b14c86bfa2597f2fb27` | Pending verification | Codex | — | — | OPEN |
| nave-48 | n=30 and mean>0 is the entire PROMISING gate. | MEDIUM | `ecc05bf0b74199daafc77b14c86bfa2597f2fb27` | Pending verification | Codex | — | — | OPEN |
| nave-48 | no volatility staleness beyond `available_at <= decision_time`. | MEDIUM | `ecc05bf0b74199daafc77b14c86bfa2597f2fb27` | Pending verification | Codex | — | — | OPEN |
| nave-48 | `StrategyState.VALIDATED` exists on the enum | LOW | `ecc05bf0b74199daafc77b14c86bfa2597f2fb27` | Pending verification | Codex | — | — | OPEN |
| nave-49 | `present_result` hardcodes `delivery.surface = "parent"` and has no `thread_id`. | HIGH | `f83cedc8328e228772150f9913cd9864ef316c57` | Pending verification | Codex | — | — | OPEN |
| nave-49 | `quant.stock_short_scan` is declared but not executable by `quant_runner`. | HIGH | `f83cedc8328e228772150f9913cd9864ef316c57` | Pending verification | Codex | — | — | OPEN |
| nave-49 | Discord text dumps raw JSON of positions/events/candidates. | MEDIUM | `f83cedc8328e228772150f9913cd9864ef316c57` | Pending verification | Codex | — | — | OPEN |
| nave-49 | scheduled `portfolio` always passes `--refresh-ledger`. | MEDIUM | `f83cedc8328e228772150f9913cd9864ef316c57` | Pending verification | Codex | — | — | OPEN |
| nave-49 | `ACTION_REQUIRED` presentation is “revisión humana,” which is correct, but missed-move/watch workflows also use that status. | MEDIUM | `f83cedc8328e228772150f9913cd9864ef316c57` | Pending verification | Codex | — | — | OPEN |
| nave-50 | nested JSON status vs outer classification. | LOW | `d0060170f0b89cfb7f9af45c7cef250ebac03247` | Pending verification | Codex | — | — | OPEN |
| nave-50 | unit test is a clock check, not a metrics check. | LOW | `d0060170f0b89cfb7f9af45c7cef250ebac03247` | Pending verification | Codex | — | — | OPEN |
