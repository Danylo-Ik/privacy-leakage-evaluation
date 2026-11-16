# Model training: masking

Rule-based, NER and LLM maskers plus degradation conditions. Output `masked_docs.jsonl` per docs/SCHEMA.md (offsets into the original text). Start from `seed_tools.apply_masking()` and `gold_conditions()`.

Note: build the name gazetteer from a generic Ukrainian name list, not from population.csv.
