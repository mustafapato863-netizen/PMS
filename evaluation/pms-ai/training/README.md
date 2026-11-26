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
