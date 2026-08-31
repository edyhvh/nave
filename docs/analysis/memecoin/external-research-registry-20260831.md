# NAVE external research registry — 2026-08-31

This registry keeps external evidence separate from the NAVE canonical panel.
The external material is used for replication, feature discovery, leakage
audits, and methodology—not as automatically trusted labels or merged training
rows. The evidence hierarchy is: A, independently reconstructed on-chain
events; B, reproducible published observational datasets; C, derived
benchmarks; D, third-party scores; E, anecdotal/social claims.

## Source disposition

| Source | Role | Disposition | Main NAVE use |
|---|---|---|---|
| NAVE Dune panel | A / primary | Canonical local source, partial horizons | Launch, trade, migration, targeted participants |
| [Slinky21 corpus](https://huggingface.co/datasets/Slinky21/Pumpfun_Memecoin_Corpus) | B / benchmark | ACTIVE; no linked completed papers found | Hypothesis discovery and regime warnings |
| [RED-PUMP-2026](https://zenodo.org/records/21923106) | B / benchmark | Relevant corrigendum, not imported | Metadata replication hypotheses |
| [RED-COHORT-2026](https://zenodo.org/records/21536881) | B / replication | Partial structural benchmark | Independent co-occurrence graph |
| [PRFS](https://arxiv.org/abs/2606.08228) | methodology | Adopted | Reject-side follow-up audit |
| [RED-2400](https://zenodo.org/records/20479610) | C / benchmark | Methodology benchmark | Five-tier reject outcome design |
| [Trenches forward capture](https://huggingface.co/datasets/Tr4m0ryp/trenches-pumpfun-forward-2026-08) | B / leakage audit | Metadata reviewed | Per-field derivability timestamps |
| [MELT](https://github.com/git-disl/MELT) | B / feature discovery | Ideas only; no large data | Bundles, fund flow, wash/co-purchase features |
| [PumpApi replayer](https://github.com/Solana-Trading-Lab/replayer-rust) | A candidate | Audit only | Possible lower-cost raw-event cross-check |
| [Graduate Oracle](https://github.com/Based-LTD/graduate-oracle) | D baseline | Documentation only | Future external baseline comparison |

## Licensing and IP

Slinky’s Hugging Face card identifies MIT while its README states CC-BY-4.0;
that conflict is unresolved, so NAVE should not redistribute or embed it until
clarified. RED-PUMP is CC-BY-4.0. RED-COHORT is CC-BY-4.0 for data and MIT for
the detector, but includes a patent notice requiring future commercial review.
PRFS and the RED-2400 toolkit are MIT; the RED-2400 data are CC-BY-4.0.
Trenches is PolyForm Noncommercial 1.0.0. MELT is CC-BY-NC-4.0 and its code or
data must not enter a future commercial dependency without legal review.
PumpApi and Graduate Oracle repository licenses were not confirmed; no code was
copied. NAVE implements generic concepts independently.

