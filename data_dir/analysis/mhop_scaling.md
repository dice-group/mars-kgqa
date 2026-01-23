### MHOP Scaling Performance

We evaluated MHOP values ranging from 1 to 20. In these experiments we fixed TOPN = 20 and activated the features: *Augmented Text Similarity*, *Concrete Examples*, *Typological Information*, and *Pattern Count*. Similar to our ablation study, all runs used the QALD‑10 English training set, which contains 333 questions.

| MHOP | Prediction Time (seconds) | Macro F1 score |
|------|---------------------------|----------|
| 1    | 2 496.34                  | 0.7284   |
| 2    | 3 833.48                  | 0.7199   |
| 3    | 4 313.99                  | 0.7149   |
| 4    | 6 033.29                  | 0.7203   |
| 5    | 5 443.97                  | 0.7173   |
| 6    | 6 762.90                  | 0.7173   |
| 7    | 6 242.63                  | 0.7173   |
| 8    | 6 302.11                  | 0.7173   |
| 9    | 5 467.33                  | 0.7173   |
| 10   | 6 625.03                  | 0.7173   |
| 20   | 6 246.85                  | 0.7173   |

The table shows that while the macro F1 score peaks at **MHOP = 1** (0.7284) and stays relatively flat thereafter (≈ 0.717 ± 0.003), the **prediction time grows substantially** as MHOP increases, roughly doubling from ~2.5 k s at MHOP 1 to >6 k s for MHOP ≥ 4. This suggests that for the QALD‑10 English training set, deeper hop reasoning yields diminishing returns in accuracy but incurs higher computational cost. Accordingly, on larger or more complex datasets where deeper multi‑hop reasoning is needed the trade‑off could become more pronounced: higher MHOP values may be required for better coverage, yet they will likely cause even larger increases in runtime. Therefore, choosing an optimal MHOP involves balancing the F1 gains against the steep rise in inference time, especially for resource‑intensive scenarios.
