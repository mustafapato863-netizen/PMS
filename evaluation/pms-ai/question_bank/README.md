# PMS assistant question bank

1000+ English questions over the synthetic eval dataset (no real employee data).
Regenerate: `cd Backend && python3 scripts/build_question_bank.py`

- `questions.jsonl`: every question with its checks (expected names or scores, forbidden text, allowed outcomes).
- `results.jsonl`: the assistant's answer on the offline deterministic path, with pass or fail.
- `train_sft.jsonl`: chat-format rows, only answers that passed their checks and are not held out.
- `heldout_questions.jsonl`: ~20% of phrasings kept out of training, for honest evaluation.
- `summary.json`: pass rate per category.

Expected facts come from the records, not from the assistant. Failures are real gaps, and become the regression list.
Limits: the synthetic data has about 25 records, so the questions vary in phrasing much more than in facts. Add real
(deidentified, thresholded) exports through the feedback pipeline before training a model for production.
