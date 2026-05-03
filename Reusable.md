The points here allow you to understand the basic structure of this repository and how to run python scripts or where to find reusable parts.
- To run any python script, you can make use of already set environment by calling: `bash pylauncher.sh normal src.some.random.script opt1 opt2`.
- We have a lot of predefined utility functions for creating files/directory or processing sparql or qald files in `src/util`.
- get_qald_answer_sparql in src/util/qald_io.py can be used to execute a sparql query on a specific endpoint. It also adds the required prefixes and returns output expected by QALD format.
- We have KGQA datasets in data_dir/processed_kgqa_ds directory. If they were not originally in QALD format, we have added the QALD formatted versions in there as well.
