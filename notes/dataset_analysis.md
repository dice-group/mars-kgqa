### How to analyze a KGQA dataset?
We can directly feed the dataset to an LLM and ask it to document different types of questions it has seen with examples. Since some datasets can be quite large, we update the document iteratively by paginating the entries in the dataset.

We perform the following steps for analysis:
1. Ask LLM to analyze batched data based on a template
2. Merge the notes iteratively into one single note

### Rationale behind dataset analysis
For the toolset to be created, we need to understand the types of questions that are contained in a particular dataset.