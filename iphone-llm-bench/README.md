# iphone-llm-bench

Raw result JSONs from Local Model Bench on-device campaigns. Each file is one
measured run of the iOS benchmark app (harness forked from
[john-rocky/apple-silicon-llm-bench](https://github.com/john-rocky/apple-silicon-llm-bench)).

Top-level fields per file: `device` (model, iOS, memory, thermal/battery state at
run start), `runtime`, `model` + `parameters` (hfRepoId, quantization), `metrics`
(prefill/decode tok/s, TTFT, memory peaks), `outputSample`, `task`, `timestamp`.

## Campaigns

- `2026-10-09-iphone-17e/` — iPhone 17e (A19, 8 GB), 30 cells, MLX / llama.cpp /
  LiteRT-LM / Apple Foundation Model. Article:
  https://localmodelbench.com/iphone-17e-local-llm-bench/
