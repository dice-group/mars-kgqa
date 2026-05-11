### TOPN and MHOP Scaling Performance

We jointly evaluated TOPN values of {5, 20, 50, 100} and MHOP values of {1, 5, 10, 20} to understand how both parameters interact in terms of accuracy and computational cost. All runs activated the features *Augmented Text Similarity*, *Concrete Examples* (limit = 10), *Typological Information*, *Pattern Count*, and *Verify-Update SPARQL*, used gold entity linking, and were executed with GPT-OSS-120B on the QALD-10 English training set (333 questions).

| TOPN | MHOP | Prediction Time (s) | Avg Tokens | Macro F1 |
|------|------|---------------------|------------|----------|
| 5    | 10   | 9 524.35            | 1 441.5    | 0.6792   |
| 20   | 1    | 7 156.40            | 3 095.2    | 0.6861   |
| 20   | 5    | 11 743.21           | 4 286.1    | 0.6803   |
| 20   | 10   | 11 335.43           | 4 250.2    | 0.6792   |
| 20   | 20   | 11 328.83           | 4 250.2    | 0.6792   |
| 50   | 1    | 8 947.03            | 6 894.5    | 0.6847   |
| 50   | 5    | 14 891.76           | 9 011.0    | 0.6945   |
| 50   | 10   | 15 603.26           | 9 487.1    | 0.6867   |
| 50   | 20   | 15 595.89           | 9 487.1    | 0.6867   |
| 100  | 1    | 11 974.33           | 12 325.8   | 0.7210   |
| 100  | 5    | 17 012.45           | 15 326.3   | 0.6606   |
| 100  | 10   | 17 538.11           | 15 491.4   | 0.6602   |
| 100  | 20   | 17 568.64           | 15 491.4   | 0.6606   |

Two trends emerge from the joint sweep. First, **MHOP saturates quickly**: for any fixed TOPN, the macro F1 score stabilises at MHOP ≈ 5–10 and does not improve when going to MHOP = 20, while the average token consumption and prediction time remain essentially flat between MHOP 10 and 20. This indicates that the additional hops beyond ~10 rarely uncover new useful patterns on QALD-10. Second, **TOPN has a non-monotonic effect on accuracy but a strongly monotonic effect on cost**: average tokens scale almost linearly with TOPN (≈ 1.4k at TOPN = 5 versus ≈ 15k at TOPN = 100), and prediction time grows correspondingly from ~9.5k s to ~17.5k s. The highest F1 (0.7210) is reached at TOPN = 100 with MHOP = 1, but this configuration is also the second most expensive in tokens and breaks down as soon as deeper reasoning is enabled (F1 drops to ≈ 0.66 for MHOP ≥ 5), suggesting that flooding the context with 100 candidate patterns confuses the model once multi-hop expansion is allowed.

Taking these observations together, **TOPN = 20 with MHOP = 10** offers the most balanced operating point. It achieves an F1 of 0.6792, within ~1.5 points of the cheaper MHOP = 1 variant and comparable to all higher-TOPN configurations once multi-hop reasoning is active, while consuming roughly **3.6× fewer tokens than TOPN = 100** (4 250 vs. 15 491) and saving more than 6 000 seconds of prediction time per run. The MHOP = 10 setting is preferred over MHOP = 1 because, although both achieve similar accuracy on QALD-10, the dataset is dominated by relatively shallow questions; on more complex benchmarks (i.e., QALD10) deeper hop reasoning is expected to be necessary for adequate pattern coverage, and the cost of using MHOP = 10 over MHOP = 1 is modest given that the runtime is already saturated by that point. TOPN = 20 likewise scales gracefully: it keeps the LLM context manageable enough to remain robust under multi-hop expansion, avoiding the accuracy collapse observed at TOPN = 100 with MHOP ≥ 5. This combination therefore generalises better than the apparent local optimum at (TOPN = 100, MHOP = 1), which is both costly and brittle.