## 1.  What keeps going wrong?  

Across the 50+ failure analyses the same handful of root‑causes keep re‑appearing.  They can be grouped into three high‑level families:

| Family | Typical symptom | Why it happens (root‑cause) |
|---|---|---|
|**A. Entity linking / grounding**| • Wrong Q‑ID (e.g. “Vladimir Lenin” for a Czech‑film query, “Forbes” → Q956568, “Millepede” → no ID).  <br>• Missing entity (no Q‑ID at all, e.g. “Free University of Amsterdam”, “Lake Chiemsee”).  <br>• Wrong sense (language → Q188 instead of country → Q183).| • The linker relies on a single‑shot lexical match or on a low‑confidence candidate and never falls back to a gold‑entity or a fuzzy search.  <br>• No disambiguation step when a label is ambiguous.  <br>• The downstream pipeline discards the gold entity if confidence < threshold. |
|**B. Relation / predicate extraction**| • Missing the predicate that actually answers the question (e.g. “flows into” → P403 never extracted, “nickname” → P1449 omitted).  <br>• Mapping a synonym to the wrong property ( “start” → P1427 instead of P559).  <br>• Only single‑hop patterns collected, so needed two‑hop chains (P176 → P17, P131 → P17, etc.) never appear.  <br>• Wrong direction of a property (using subject→object when the inverse is needed).| • The relation extractor has a very small lexical dictionary; many paraphrases are unseen.  <br>• The extractor is hard‑wired to a maximum hop count (often 1) and therefore prunes useful multi‑hop paths.  <br>• No fallback to a generic “search‑by‑label → property” step. |
|**C. Pattern‑selection & LLM‑generation**| • The *relevant* triple pattern never makes it into the top‑N list, so the model cannot pick it (e.g. P1104 for page‑count, P495 for country‑of‑origin, P2043 for river length).  <br>• The similarity scorer is tuned to surface the most frequent or highest‑scoring patterns, not the ones hinted by the question.  <br>• The LLM is free to hallucinate new predicates/IDs because the prompt does not force “use only the supplied patterns”.  <br>• Missing PREFIX block, missing `DISTINCT`, missing label service, missing type constraints.  <br>• Post‑processing strips required tokens (`SPARQL:`) or adds unwanted filters. | • Scoring function does not weight keyword‑predicate overlap strongly enough.  <br>• The prompt template does not explicitly forbid inventing predicates or entities.  <br>• No validation step that checks the generated query only uses IDs that appear in the candidate‑pattern list.  <br>• The generator is not instructed to keep boiler‑plate (PREFIXes, `SERVICE wikibase:label`, etc.). |

### Recurring concrete patterns

| Pattern | What went wrong |
|---|---|
|**Wrong class/entity** – e.g. “car” → Q3231690, “company” → Q4830453, “German” → language Q188|Entity linker chose a sibling or a generic class instead of the target.|
|**Missing property** – e.g. “flows into” → P403, “nickname” → P1449, “population density” → P2589|Relation extractor did not recognise the synonym or the multi‑hop chain required.|
|**Pattern not in top‑N** – e.g. P1104 (pages), P2043 (river length), P495 (country‑of‑origin)|Scorer gave higher rank to more common or generic patterns, pushing the needed ones out of the shortlist.|
|**Hallucinated predicate** – e.g. inventing P463 (membership), P576 (date of admission) when not present|Prompt did not prevent the LLM from adding unseen predicates.|
|**Missing PREFIX / boiler‑plate**|Prompt omitted the requirement for a `PREFIX` block or the “SPARQL:” token; post‑processor stripped it.|
|**Incorrect direction / inverse property** – e.g. using `wdt:P22` (father) instead of the inverse `wdt:P40` (child) for parent queries|Extractor never generated inverse patterns.|
|**Insufficient hop depth** – only 1‑hop patterns offered, while answer needs 2‑hop (P176 → P17, P131 → P17, etc.)|Hard‑coded `max_hops=1`.|
|**Disambiguation failures** – “Veganism” vs “vegetarianism”, “James Bond” character vs film series|Linker picks the most popular sense without context filtering.|

---

## 2.  How to fix it – a road‑map of improvements  

Below is a checklist that addresses the three families of failures.  The items are ordered from *low‑effort/high‑impact* to *more structural* changes, but all are required for a robust end‑to‑end system.

### 2.1  Strengthen the **entity‑linking** stage  

| Improvement | Why it helps | Implementation notes |
|---|---|---|
|**a. Two‑tier linking (candidate generation + disambiguation)**|Provides a ranked list of possible Q‑IDs; the gold entity can be rescued if the top‑1 is wrong.|Use a fast lexical lookup (e.g. Wikidata search API) to get *all* matches, then re‑rank with a contextual model (BERT/BART) that looks at the whole question.|
|**b. Synonym / alias dictionary**|Catches “taikonaut”, “free university of amsterdam”, “German” (country) etc.|Populate from Wikidata “also known as” (`skos:altLabel`) and from external vocabularies (DBpedia, WordNet).|
|**c. Confidence‑threshold fallback**|If the top candidate is below X % confidence, automatically insert the gold ID (when available) or request a second‑pass search.|Expose the threshold as a configurable parameter; log fallback events for later analysis.|
|**d. Entity‑type filter**|Ensures the chosen Q‑ID belongs to the expected class (e.g. a *film* when the question asks about a *movie*).|After candidate generation, query `wdt:P31/wdt:P279*` for each candidate and keep only those whose type matches the expected type derived from the question.|
|**e. Post‑linking validation**|Catches impossible IDs (e.g. “Q956568” for Forbes) before they reach the pattern extractor.|Simple sanity check: does the candidate have a `wdt:P31` that matches a “website” or “organisation”?|

### 2.2  Enrich **relation / predicate extraction**  

| Improvement | Why it helps | Implementation notes |
|---|---|---|
|**a. Expanded lexical mapping**|Maps many paraphrases (“flows into”, “empties into”, “mouth of”, “named after”) to the correct P‑ID.|Build a phrase‑to‑P dictionary from Wikidata property aliases plus a crowdsourced list of common synonyms.|
|**b. Multi‑hop pattern generator**|Allows the system to collect 2‑ or 3‑hop chains that are often required (P176 → P17, P131 → P17, etc.).|Set `max_hops` ≥ 2 (or make it dynamic based on question length).  When generating patterns, keep the intermediate nodes so the LLM can stitch them together.|
|**c. Inverse‑property generation**|Provides both directions of a predicate, enabling queries that need the child→parent direction.|For every extracted predicate also add `?obj wdt:<inverse(P)> ?subj` (or rely on Wikidata’s `wdt:P*` which is already directional but expose the reverse in the candidate list).|
|**d. Type‑aware pattern ranking**|Prioritises patterns that involve the expected class (e.g. `P31 wd:Q11424` for films).|When scoring a triple, boost its weight if the predicate’s domain/range matches the entity‑type identified earlier.|
|**e. Property‑coverage check**|Detects when a crucial predicate (e.g. P1104, P2043, P495) is missing from the top‑N and forces a re‑run with a larger `top_n`.|After the first scoring pass, compare required keywords against the retrieved P‑IDs; if any are missing, increase `top_n` and/or widen the similarity threshold.|

### 2.3  Constrain the **LLM generation**  

| Improvement | Why it helps | Implementation notes |
|---|---|---|
|**a. “Use only supplied IDs” prompt clause**|Stops the model from hallucinating new Q‑IDs or P‑IDs. |Explicitly state: *“You may only use the entities and predicates that appear in the list below. Do NOT invent any new IDs.”*|
|**b. Boiler‑plate template**|Ensures PREFIX block, `DISTINCT`, label service, and required output token (`SPARQL:`).|Provide a fixed header in the prompt and ask the model to paste the query *after* the header.|
|**c. Post‑generation whitelist validator**|Catches any ID that was not in the candidate list (or not in an allowed whitelist).|After the model outputs, parse the SPARQL, compare each Q‑/P‑ID against the supplied set; if a mismatch, either reject or invoke a repair loop.|
|**d. Formal query‑shape enforcement**|Guarantees required filters (type, subclass‐of, country, etc.) are present.|Add a secondary prompt: *“Check that the query contains a triple with the predicate `<expected P>` and the variable `<expected var>`.”*|
|**e. Syntax‑post‑processor**|Adds missing PREFIXes, inserts `SERVICE wikibase:label`, removes stray whitespace, guarantees `SPARQL:` token.|A lightweight rule‑based formatter runs after generation, before answer validation.|
|**f. Beam/Multiple‑candidate generation**|If the first answer fails validation, ask the LLM for an alternative using the same pattern list. |Keep a small beam (2‑3) and pick the first that passes the whitelist & syntax checks.|
|**g. Confidence‑aware fallback**|When no valid query can be produced, fall back to a “search‑by‑label” engine rather than returning a wrong SPARQL. |Log the failure for later model improvement. |

### 2.4  Improve **pattern‑ranking / similarity scoring**  

| Improvement | Why it helps | Implementation notes |
|---|---|---|
|**a. Keyword‑predicate overlap weighting**|Boosts patterns that contain terms appearing in the question (e.g., “nickname”, “population density”).|Compute TF‑IDF similarity between question tokens and predicate labels/aliases.|
|**b. Type‑based bias**|Ensures that patterns involving the expected entity type rise to the top. |Add a multiplicative factor based on the domain/range match from step 2.1.|
|**c. Multi‑objective scoring (relevance + coverage)**|Balances selecting a single highly‑relevant triple versus a set that together covers all needed constraints. |Use a greedy set‑cover heuristic: pick the triple that adds the most uncovered required predicates.|
|**d. Dynamic `top_n` per question**|Longer, more complex questions need more candidates. |If the question contains > N keywords, increase `top_n` automatically.|
|**e. Feedback loop from validation**|If the whitelist validator rejects a generated query, feed that back to re‑rank patterns (e.g., penalise missing predicates).|Simple reinforcement‑learning style update or a rule‑based re‑run. |

### 2.5  **System‑wide safeguards**  

1. **Logging & error analysis** – record every step (entity candidates, extracted predicates, top‑N list, LLM output, validation result).  This makes it easy to spot recurring gaps (e.g., “P2043 never appears for rivers”).  
2. **Test suite of known failure modes** – create a small “regression” set that explicitly contains the patterns above (wrong entity, missing predicate, hallucinated ID).  Run the pipeline after each change to verify the fix.  
3. **Graceful degradation** – if the pipeline cannot produce a valid SPARQL, return a clear “I could not find enough information” message rather than an incorrect query.  

---

## 3.  Summary checklist (what to fix first)

| Priority | Action | Component | Brief |
|---|---|---|---|
|**1**|Add a “use‑only‑provided‑IDs” clause + whitelist validator|LLM prompt & post‑processor|Stops hallucination, the most frequent error.|
|**2**|Expand entity‑linker synonym dictionary & add fallback to gold IDs|Entity linker|Fixes the majority of wrong‑entity cases.|
|**3**|Increase `max_hops` to 2 (or dynamic) and generate inverse properties|Relation extractor|Enables needed multi‑hop chains (P176 → P17, P131 → P17, etc.).|
|**4**|Boost predicate‑keyword overlap in pattern‑ranking|Scorer|Brings missing but crucial predicates (P1104, P2043, P495) into top‑N.|
|**5**|Provide a fixed SPARQL header template (PREFIXes, `SPARQL:` token, label service)|Prompt / post‑processor|Eliminates format‑related mismatches.|
|**6**|Add type‑aware filtering of candidate entities and predicates|Entity linking & extractor|Prevents “German” → language, “car” → generic model, etc.|
|**7**|Implement multi‑candidate (beam) generation + validation loop|LLM generator|Allows the system to recover when the first draft fails validation.|
|**8**|Log and monitor missing‑predicate warnings; auto‑increase `top_n` when needed|Scorer / orchestrator|Ensures coverage for complex queries.|
|**9**|Introduce a small “fallback search‑by‑label” path when no valid query can be built|Overall pipeline|Graceful failure instead of wrong answer.|
|**10**|Run regression suite covering all identified failure patterns after each change|QA process|Guarantees that fixes stay effective.|

Implementing these steps systematically will close the gaps that currently let the pipeline miss the right entities, drop essential predicates, invent IDs, or output syntactically incomplete SPARQL.  The end result should be a system that **(i)** reliably grounds the question in the correct Wikidata items, **(ii)** supplies the LLM with a rich but constrained set of relevant triple patterns (including multi‑hop and inverse links), **(iii)** forces the model to stay within that set and to emit a complete, correctly‑prefixed query, and **(iv)** validates the output before it reaches the evaluator.