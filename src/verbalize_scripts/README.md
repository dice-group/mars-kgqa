Scripts to verbalize the KG triples and vectorize them.

Step 1: Find all the rdfs:labels statements in the KG using `src/verbalize_scripts/label_grep.sh`.
Step 2: Generate a map/dict of entities and their labels using `src/verbalize_scripts/label_map_gen.py`.
Step 3: Split the N-triples into smaller chunks for multiprocessing using `src/verbalize_scripts/split_ntriples.sh`.
Step 4: Generate triple verbalizations for each chunk using `src/verbalize_scripts/set_chunk_verbalize_jobs.py`.
Step 5: Generate embeddings for each verbalized chunk.
Step 6: Load embeddings and verbalizations to a vector database.
Step 7: Fetch nearest neighbour triples for all possible question strings.