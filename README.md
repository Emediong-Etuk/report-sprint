# One Honest Bot Is Enough: Breaking Up Price Collusion Between Learning Pricing Bots

AI Agent Collusion Research Sprint (Apart Research, Poseidon Research, AE Studio), October 23-25, 2026.
Track 1 (Markets and Collusion), question 1.5: *which single restriction removes the most collusion at the least cost?*

**Report:** [`report/report.pdf`](report/report.pdf) (Word version: [`report/report.docx`](report/report.docx))

## What we did
Two Q-learning pricing bots compete in the standard market from Calvano et al. (2020). With no rules they learn to keep
prices high together and to punish a rival who cuts its price. We then tried four single changes, one at a time, with
50 seeds each:

| Setting | Collusion index (0 = fair, 1 = cartel) | Who must change |
|---|---|---|
| No restriction | 0.83 ± 0.03 | nobody |
| Hide rival prices | 0.96 ± 0.01 (worse) | all sellers / platform |
| Add a third seller | 0.64 ± 0.01 | a new seller |
| Force 5% random prices | 0.43 ± 0.05 | all sellers |
| **Swap one bot for a no-regret (Hedge) bot** | **0.08 ± 0.01** | **one seller** |

## How to run (laptop CPU, no GPU, no API keys, ~15 minutes)
```bash
pip install -r requirements.txt
python src/run_experiment.py      # writes results/summary.json and results/raw_results.json
python src/make_figures.py        # writes figures/*.png
python report/build_report.py     # writes report/report.docx and report.pdf (needs LibreOffice for the PDF)
```
Use `python src/run_experiment.py --seeds 5` for a quick check.

## Files
- `src/market.py` - the market, the Q-learning bot, the Hedge bot and the cheat test
- `src/run_experiment.py` - all settings, the dose sweep and the robustness checks
- `src/make_figures.py` - figures
- `results/` - raw results for every seed and the summary
- `report/` - the report and the script that builds it

## Prior work
All code was written during the sprint. Nothing here is preexisting code. The market and learning settings follow
the published method of Calvano et al. (2020); the Hedge algorithm follows Freund and Schapire (1997).
