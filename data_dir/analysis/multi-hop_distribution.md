# Multi-Hop Query Analysis

| Dataset | Total Qs | Analyzed | Skipped | Errors |
|---------|----------|----------|---------|--------|
| lcquad2/test | 4624 | 4624 | 0 | 0 |
| qald10/test | 383 | 382 | 0 | 1 |
| qald9plus/test | 127 | 127 | 0 | 0 |

## Hop Distribution

| Dataset |0-hop | 1-hop | 2-hop | 3-hop | 4-hop | Total |
|---------|---|---|---|---|---|-------|
| lcquad2/test | 3 | 3050 | 1571 | 0 | 0 | 4624 |
| qald10/test | 0 | 268 | 97 | 14 | 3 | 382 |
| qald9plus/test | 0 | 97 | 29 | 1 | 0 | 127 |
| **Total** | 3 | 3415 | 1697 | 15 | 3 | 5133 |

## Percentage Distribution

| Dataset |0-hop (%) | 1-hop (%) | 2-hop (%) | 3-hop (%) | 4-hop (%) |
|---------|---|---|---|---|---|
| lcquad2/test | 0.1 | 66.0 | 34.0 | 0.0 | 0.0 |
| qald10/test | 0.0 | 70.2 | 25.4 | 3.7 | 0.8 |
| qald9plus/test | 0.0 | 76.4 | 22.8 | 0.8 | 0.0 |
| **Total** | 0.1 | 66.5 | 33.1 | 0.3 | 0.1 |
