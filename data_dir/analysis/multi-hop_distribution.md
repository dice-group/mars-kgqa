# Multi-Hop Query Analysis

| Dataset | Total Qs | Analyzed | Skipped | Errors |
|---------|----------|----------|---------|--------|
| lcquad2/test | 4624 | 4624 | 0 | 0 |
| qald10/test | 383 | 382 | 0 | 1 |
| qald9plus/test | 127 | 127 | 0 | 0 |
| qald9plus/train | 348 | 348 | 0 | 0 |
| spinach/test | 125 | 123 | 0 | 2 |
| spinach/train | 125 | 118 | 0 | 7 |
| spinach_qald9plus_combined/train | 473 | 466 | 0 | 7 |

## Hop Distribution

| Dataset |0-hop | 1-hop | 2-hop | 3-hop | 4-hop | 5-hop | Total |
|---------|---|---|---|---|---|---|-------|
| lcquad2/test | 3 | 3050 | 1571 | 0 | 0 | 0 | 4624 |
| qald10/test | 0 | 268 | 97 | 14 | 3 | 0 | 382 |
| qald9plus/test | 0 | 97 | 29 | 1 | 0 | 0 | 127 |
| qald9plus/train | 0 | 285 | 60 | 3 | 0 | 0 | 348 |
| spinach/test | 6 | 38 | 59 | 13 | 6 | 1 | 123 |
| spinach/train | 7 | 43 | 47 | 17 | 4 | 0 | 118 |
| spinach_qald9plus_combined/train | 7 | 328 | 107 | 20 | 4 | 0 | 466 |
| **Total** | 23 | 4109 | 1970 | 68 | 17 | 1 | 6188 |

## Percentage Distribution

| Dataset |0-hop (%) | 1-hop (%) | 2-hop (%) | 3-hop (%) | 4-hop (%) | 5-hop (%) |
|---------|---|---|---|---|---|---|
| lcquad2/test | 0.1 | 66.0 | 34.0 | 0.0 | 0.0 | 0.0 |
| qald10/test | 0.0 | 70.2 | 25.4 | 3.7 | 0.8 | 0.0 |
| qald9plus/test | 0.0 | 76.4 | 22.8 | 0.8 | 0.0 | 0.0 |
| qald9plus/train | 0.0 | 81.9 | 17.2 | 0.9 | 0.0 | 0.0 |
| spinach/test | 4.9 | 30.9 | 48.0 | 10.6 | 4.9 | 0.8 |
| spinach/train | 5.9 | 36.4 | 39.8 | 14.4 | 3.4 | 0.0 |
| spinach_qald9plus_combined/train | 1.5 | 70.4 | 23.0 | 4.3 | 0.9 | 0.0 |
| **Total** | 0.4 | 66.4 | 31.8 | 1.1 | 0.3 | 0.0 |
