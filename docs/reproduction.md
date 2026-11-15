# Reproduce the local run

Run the setup in the README with Python 3.12. Olist v2 is pinned in the downloader and builder. The build produces `data/olist.duckdb` and `data/olist.manifest.json`. The sample digest is platform independent. DuckDB file bytes may vary with physical storage.

## Local model

The measured run used Qwen2.5-Coder-3B-Instruct Q4_K_M at Hugging Face revision `f74adce6aa16316c625447af059dbebe4983757c`. The GGUF takes 2.10 GB and has SHA-256 `724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7`. Use the llama.cpp b12383 release for your OS and device. [Pinned Qwen weights](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/tree/f74adce6aa16316c625447af059dbebe4983757c), [llama.cpp b12383](https://github.com/ggml-org/llama.cpp/releases/tag/b12383)

```sh
llama-server --list-devices
llama-server -m data/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf -ngl 99 -c 4096 -np 1 --host 127.0.0.1 --port 8080 --alias commercelens-local
```

The Windows measurement selected the RTX 4060 with `--device Vulkan1`. Choose the device shown on your machine. Use `-ngl 0` for CPU execution. The HTTP adapter requests JSON output, temperature zero, seed 741 and up to 384 generated tokens. Hardware and backend changes may affect latency and generation. In shared environments, configure an API key or isolate access to the local endpoint.

Set `COMMERCE_MODEL_URL` to change the API base, `COMMERCE_MODEL` to change the alias, and `COMMERCE_MODEL_API_KEY` for headers as needed. The default is local. A remote endpoint requires HTTPS and the explicit `COMMERCE_ENABLE_REMOTE_MODEL=1` setting. Local calls cost $0 in metered API fees. Electricity and hardware cost were not measured.

## Benchmarks and demo

```sh
python -m benchmarks.databench --fetch
python -m benchmarks.run olist --output reports/runs/olist
python -m benchmarks.run databench --output reports/runs/databench
python -m streamlit run app/streamlit_app.py
```

The harness writes per-task JSONL and aggregate JSON. Keep the raw outputs local because they may include sampled values and benchmark data. Streamlit's Natural language mode shows live tool evidence and the Preconfigured metric mode runs the same analysis tool with selected input parameters. The FastAPI routes are `GET /health`, `POST /ask` and `POST /investigate`. Bind the HTTP service to localhost for the documented setup.

## Three-minute showcase

With Olist built and the local model serving, open the Streamlit URL and use **Natural language** for each example. The sidebar marks the questions as editable examples.

1. **Delivery performance.** Click **Run analysis**. Compare July's 30/936 eligible deliveries with June's 15/917. Read the state contribution chart, query evidence and retrieved definitions. Expand **Executed SQL** to inspect purchase windows and eligible counts.
2. **Merchandise performance.** Run the July versus June comparison by product category. The item-price totals are R$141,625.90 and R$139,360.38. Inspect signed category contributions. Optionally run **Recorded payment value** to see the separate order-level proxy, R$166,395.04 versus R$162,715.53.
3. **Inventory evidence limits.** Run the warehouse shortage question. The system should mark it unconfirmed. Open the execution trace to see the selected unsupported route.

Click **Download report** in each run to save the executed report as JSON. The browser check used the real local model and the pinned Olist database. To independently verify the numeric examples from the raw source tables:

```powershell
$env:COMMERCE_VERIFY_OLIST_DB = (Resolve-Path "data/olist.duckdb").Path
python -m pytest -q tests/test_showcase_olist.py
```

The regular CI suite runs without the publisher archive. Set the variable after the documented data build to enable the three real-data checks.
