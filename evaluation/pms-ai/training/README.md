# Training the PMS assistant (free path)

Nothing here runs automatically. No paid usage.

1. Open `pms_lora_colab.ipynb` in Google Colab (free T4 GPU). Run all cells. About 30-60 min for 759 rows x 2 epochs.
2. Download `pms-adapter.zip` (adapter_config.json with model_type "mistral" + adapter_model.safetensors, rank 16, well under 300MB).
3. Upload to Cloudflare Workers AI (open beta, free during beta; rank <= 32; base must be non-quantized `@cf/mistralai/mistral-7b-instruct-v0.2-lora`):
   `npx wrangler ai finetune create @cf/mistralai/mistral-7b-instruct-v0.2-lora pms-assistant ./adapter`
   Docs: https://developers.cloudflare.com/workers-ai/features/fine-tunes/loras/
4. Evaluate: send the held-out questions (`question_bank/heldout_questions.jsonl`) through the adapter by passing `lora: "pms-assistant"` in the Workers AI call, score with the same checks as `Backend/scripts/build_question_bank.py`. Only route traffic to it if it beats the current model on held-out accuracy and never invents numbers.
5. Rollout would be a flag-guarded provider option, free tier daily neuron caps unchanged.

Caveats: training data is synthetic (25 records), so the model learns phrasing and answer style, not real facts. Numbers must keep coming from the deterministic tools. Add deidentified real exports through the feedback pipeline before expecting production gains. Cloudflare free plan inference still counts against the daily neuron budget shared with chat fallback.

## Update (grounded format, Nov 27 2026)
Held-out eval of the first adapter (pms-assistant-v2): with no facts in the prompt it invented numbers in 192/196 answers (current granite: 0/196); even with correct facts it added made-up codes and ranks. Cause: closed-book training rows. The notebook now trains on `grounded_train.jsonl`: the prompt carries "Verified facts: {...}" from the deterministic tools, the model only phrases them, about 20% refusal rows ("Verified facts: none"), and thin-fact rows that teach it not to add rank/code/grade when they are not given.

Build: `python Backend/scripts/build_grounded_sft.py --out evaluation/pms-ai/training [--export export.json --names names.txt]`
Real data: pass the Admin-reviewed export from `GET /api/ai/traces/export?verified_only=true` (reviewer_verified only, k>=5 cohorts via the feedback bundle). Rows containing a name from `--names`, an email or a phone are dropped. A person must read `leak_report.txt` and its random sample before the file leaves the server; stop if anything looks identifying.
Model name on Workers AI is `@cf/mistral/mistral-7b-instruct-v0.2-lora` (not "mistralai"); the notebook sets adapter_config base_model_name_or_path to `mistralai/Mistral-7B-Instruct-v0.2`.
Shadow mode (PR for `PMS_AI_CUSTOM_MODEL=shadow`) logs metrics only; promotion gate: 0 invented numbers in closed-book and grounded arms, fact recall at least equal to the current model, 2 weeks stable.
