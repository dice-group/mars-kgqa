# SPARQL & Answer Set Comparison Report: qald9plus

- **Gold file**: `data_dir/processed_kgqa_ds/qald9plus/test/gerbil-ready_tentrismain_aug_gold.json`
- **Pred file**: `data_dir/best_1/processed_kgqa_ds/qald9plus/test/prediction/tentrismain_aug_gold/json/gerbil-ready_en__noctua2__PBSG_MHOP__t20-h10-pc-ausm-grasp-el-exlim10-clsinf-verupdt__gptoss120b.json`
- **Common questions**: 127

## SPARQL Comparison
| Metric | Count | Rate |
|--------|-------|------|
| Exact match | 0 | 0.0% |
| Normalized match | 18 | 14.17% |
| Loose match (no DISTINCT) | 34 | 26.77% |

## Answer Set Comparison
| Metric | Value |
|--------|-------|
| Exact match (all) | 62 (48.82%) |
| Avg Precision (all) | 0.6274 |
| Avg Recall (all) | 0.6 |
| Avg F1 (all) | 0.5871 |
| Answered questions | 99 |
| Avg Precision (answered) | 0.7846 |
| Avg Recall (answered) | 0.7495 |
| Avg F1 (answered) | 0.733 |

## Categories (answered questions only)
| Category | Count |
|----------|-------|
| Correct SPARQL + Correct Answer | 34 |
| Correct SPARQL + Wrong Answer | 0 |
| Wrong SPARQL + Correct Answer | 26 |
| Wrong SPARQL + Wrong Answer | 39 |
| Both empty | 2 |
| Gold empty, Pred has answers | 1 |
| Gold has answers, Pred empty | 25 |

## Mismatch Summary
- SPARQL mismatches: 93
- Answer mismatches (both non-empty): 39
- Pred misses (gold has, pred empty): 25
- Pred spurious (gold empty, pred has): 1

## Pred Miss Details (gold has answers, prediction empty)
| ID | Question (EN) | Gold Answers |
|----|---------------|--------------|
| 10 | How many students does the Free University of Amsterdam have? | 41000.0 (literal) |
| 13 | Which politicians were married to a German? | http://www.wikidata.org/entity/Q1002890 (uri), http://www.wikidata.org/entity/Q100765 (uri), http://www.wikidata.org/entity/Q101192 (uri), http://www.wikidata.org/entity/Q101327 (uri), http://www.wikidata.org/entity/Q101357 (uri) +1346 more |
| 27 | Which rivers flow into the North Sea? | http://www.wikidata.org/entity/Q11254034 (uri), http://www.wikidata.org/entity/Q12067337 (uri), http://www.wikidata.org/entity/Q121536791 (uri), http://www.wikidata.org/entity/Q1345836 (uri), http://www.wikidata.org/entity/Q1433715 (uri) +62 more |
| 34 | Give me all female German chancellors. | http://www.wikidata.org/entity/Q567 (uri) |
| 38 | Give me all Frisian islands that belong to the Netherlands. | http://www.wikidata.org/entity/Q1342240 (uri), http://www.wikidata.org/entity/Q1479319 (uri), http://www.wikidata.org/entity/Q1546490 (uri), http://www.wikidata.org/entity/Q1640819 (uri), http://www.wikidata.org/entity/Q1758944 (uri) +5 more |
| 39 | Which poet wrote the most books? | http://www.wikidata.org/entity/Q318391 (uri) |
| 42 | Which countries have places with more than two caves? | http://www.wikidata.org/entity/Q1016 (uri), http://www.wikidata.org/entity/Q1019 (uri), http://www.wikidata.org/entity/Q1028 (uri), http://www.wikidata.org/entity/Q1030 (uri), http://www.wikidata.org/entity/Q1033 (uri) +113 more |
| 50 | What is the highest volcano in Africa? | http://www.wikidata.org/entity/Q7296 (uri) |
| 51 | When is the movie Worst Case Scenario going to be in cinemas in the Netherlands? | 2008-01-30T00:00:00Z (literal) |
| 66 | Which artists were born on the same date as Rachel Stevens? | http://www.wikidata.org/entity/Q11473351 (uri), http://www.wikidata.org/entity/Q11587490 (uri), http://www.wikidata.org/entity/Q11589525 (uri), http://www.wikidata.org/entity/Q124656004 (uri), http://www.wikidata.org/entity/Q128840418 (uri) +25 more |
| 80 | Give me a list of all critically endangered birds. | http://www.wikidata.org/entity/Q1002627 (uri), http://www.wikidata.org/entity/Q1007804 (uri), http://www.wikidata.org/entity/Q1027765 (uri), http://www.wikidata.org/entity/Q1040304 (uri), http://www.wikidata.org/entity/Q1040426 (uri) +216 more |
| 97 | Give me the official websites of actors of the television show Charmed. | http://www.alyssa.com (uri), http://www.tedking.com/ (uri), https://www.rosemcgowan.com/ (uri) |
| 108 | When did Paraguay proclaim its independence? | 1811-01-01T00:00:00Z (literal) |
| 135 | When did Michael Jackson die? | 2009-06-25T00:00:00Z (literal) |
| 149 | Which U.S. state has the highest population density? | http://www.wikidata.org/entity/Q1408 (uri) |
| 151 | Give me all B-sides of the Ramones. | http://www.wikidata.org/entity/Q91353165 (uri) |
| 165 | What is the name of the university where Obama's wife studied? | http://www.wikidata.org/entity/Q13371 (uri), http://www.wikidata.org/entity/Q14712798 (uri), http://www.wikidata.org/entity/Q21578 (uri) |
| 166 | Which computer scientist won an oscar? | http://www.wikidata.org/entity/Q11313 (uri), http://www.wikidata.org/entity/Q15428745 (uri), http://www.wikidata.org/entity/Q22112168 (uri), http://www.wikidata.org/entity/Q22115326 (uri), http://www.wikidata.org/entity/Q22937455 (uri) +11 more |
| 179 | What were the names of the three ships by Columbus? | http://www.wikidata.org/entity/Q107900 (uri), http://www.wikidata.org/entity/Q501355 (uri) |
| 192 | Which museum exhibits The Scream by Munch? | http://www.wikidata.org/entity/Q1132918 (uri), http://www.wikidata.org/entity/Q3330707 (uri), http://www.wikidata.org/entity/Q844926 (uri) |
| 203 | How did Michael Jackson die? | http://www.wikidata.org/entity/Q12152 (uri) |
| 207 | Which daughters of British earls died at the same place they were born at? | http://www.wikidata.org/entity/Q1388169 (uri) |
| 209 | Give me all taikonauts. | http://www.wikidata.org/entity/Q107258209 (uri), http://www.wikidata.org/entity/Q112206264 (uri), http://www.wikidata.org/entity/Q114690441 (uri), http://www.wikidata.org/entity/Q118799016 (uri), http://www.wikidata.org/entity/Q118799052 (uri) +29 more |
| 211 | Give me all American presidents of the last 20 years. | http://www.wikidata.org/entity/Q207 (uri), http://www.wikidata.org/entity/Q22686 (uri), http://www.wikidata.org/entity/Q6279 (uri), http://www.wikidata.org/entity/Q76 (uri), http://www.wikidata.org/entity/Q96181216 (uri) |
| 212 | Which companies work in the aerospace industry as well as in medicine? | http://www.wikidata.org/entity/Q898208 (uri) |

## Pred Spurious Details (gold empty, prediction has answers)
| ID | Question (EN) | Pred Answers |
|----|---------------|--------------|
| 79 | Are there any castles in the United States? | http://www.wikidata.org/entity/Q15240440 (uri) |

## Answer Mismatch Details (both non-empty, but differ)
| ID | Q (EN) | Gold # | Pred # | P | R | F1 | SPARQL match |
|----|--------|--------|--------|---|---|-----|-------------|
| 7 | Give me all cars that are produced in Germany. | 119 | 45 | 0.0 | 0.0 | 0.0 | no |
| 15 | How short is the shortest active NBA player? | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 19 | Who became president after JFK died? | 1 | 4 | 0.0 | 0.0 | 0.0 | no |
| 29 | Which countries in the European Union adopted the ... | 21 | 21 | 0.9524 | 0.9524 | 0.9524 | no |
| 43 | Give me the websites of companies with more than 5... | 30 | 4 | 0.25 | 0.0333 | 0.0588 | no |
| 44 | Which European countries have a constitutional mon... | 5 | 11 | 0.4545 | 1.0 | 0.625 | no |
| 49 | Which frequent flyer program has the most airlines... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 52 | Give me all movies with Tom Cruise. | 60 | 55 | 1.0 | 0.9167 | 0.9565 | no |
| 59 | Which space probes were sent into orbit around the... | 30 | 2 | 1.0 | 0.0667 | 0.125 | no |
| 60 | Who is the governor of Texas? | 45 | 1 | 1.0 | 0.0222 | 0.0435 | no |
| 63 | Who was called Scarface? | 3 | 2 | 1.0 | 0.6667 | 0.8 | no |
| 71 | Give me all spacecrafts that flew to Mars. | 10 | 13 | 0.0 | 0.0 | 0.0 | no |
| 84 | Which American presidents were in office during th... | 3 | 5 | 0.6 | 1.0 | 0.75 | no |
| 86 | What is the highest mountain in Germany? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 87 | Which book has the most pages? | 1 | 2 | 0.0 | 0.0 | 0.0 | no |
| 95 | Who is the youngest player in the Premier League? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 103 | Where does Piccadilly start? | 2 | 2 | 0.0 | 0.0 | 0.0 | no |
| 105 | Which countries have more than ten volcanoes? | 48 | 51 | 0.5294 | 0.5625 | 0.5455 | no |
| 113 | Which German cities have more than 250000 inhabita... | 2 | 30 | 0.0667 | 1.0 | 0.125 | no |
| 115 | How many rivers and lakes are in South Carolina? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 116 | Who was called Rodzilla? | 2 | 1 | 1.0 | 0.5 | 0.6667 | no |
| 134 | What is Batman's real name? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 136 | How many moons does Mars have? | 21 | 1 | 0.0 | 0.0 | 0.0 | no |
| 138 | Give me the capitals of all countries in Africa. | 58 | 57 | 1.0 | 0.9828 | 0.9913 | no |
| 139 | Which professional surfers were born in Australia? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 140 | How many scientists graduated from an Ivy League u... | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 145 | Who owns Aldi? | 2 | 1 | 0.0 | 0.0 | 0.0 | no |
| 156 | Where is Fort Knox located? | 4 | 5 | 0.6 | 0.75 | 0.6667 | no |
| 157 | Give me English actors starring in Lovesick. | 2 | 1 | 0.0 | 0.0 | 0.0 | no |
| 158 | Give me all writers that won the Nobel Prize in li... | 119 | 122 | 0.9754 | 1.0 | 0.9876 | no |
| 169 | Give me all libraries established before 1400. | 96 | 22 | 1.0 | 0.2292 | 0.3729 | no |
| 177 | Which bridges are of the same type as the Manhatta... | 24512 | 1000 | 1.0 | 0.0408 | 0.0784 | no |
| 178 | How many James Bond movies do exist? | 1 | 1 | 0.0 | 0.0 | 0.0 | no |
| 181 | Through which countries does the Yenisei river flo... | 1 | 2 | 0.5 | 1.0 | 0.6667 | no |
| 182 | Which animals are critically endangered? | 9469 | 1000 | 1.0 | 0.1056 | 0.191 | no |
| 199 | Give me all Argentine films. | 4088 | 1 | 0.0 | 0.0 | 0.0 | no |
| 201 | What is the founding year of the brewery that prod... | 2 | 1 | 1.0 | 0.5 | 0.6667 | no |
| 213 | Show me all Czech movies. | 8376 | 1000 | 1.0 | 0.1194 | 0.2133 | no |
| 214 | Give me all professional skateboarders from Sweden... | 4 | 4 | 0.75 | 0.75 | 0.75 | no |
