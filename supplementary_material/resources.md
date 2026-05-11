# Resources

## Datasets

| Resource | Link |
|----------|------|
| Wikidata main split (underlying KG) | [main_wd22012026.nt.zst](https://files.dice-research.org/projects/MARS/EKAW/main_wd22012026.nt.zst) |
| Updated KGQA datasets | [processed_kgqa_ds](../data_dir/processed_kgqa_ds) |

- The KGQA dataset answers were updated against the Wikidata main split above, downloaded on 22.01.2026
- Wikidata split follows specifications at https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split
- The Wikidata main split contains around 11 billion triples

## Tooling

| Tool | Link |
|------|------|
| Wikidata split utility | [wikidata_prep/](../wikidata_prep/) |
| Entity linking (Grasp) | [ANNOTATION_PIPELINE.md](https://github.com/dice-group/grasp_el/blob/main/ANNOTATION_PIPELINE.md) |

The [wikidata_prep](../wikidata_prep/) directory contains scripts to download the latest Wikidata dump and extract the main/scholarly split following the official [WDQS graph split](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_graph_split) specifications. It also includes the Tentris SPARQL endpoint configuration and loading scripts.
