# Evaluation datasets and baselines

Two things live here, and they are versioned differently on purpose.

## `golden-v1.jsonl` — the labelled question set

This is the foundation of every quality claim in the PRD, and the artefact most likely to be
wrong in a way nobody notices.

**The current contents are a seed, not a labelled set.** Every `relevant_document_ids` entry
names a document id like `doc-hr-leave` that does not exist yet — phase 2 creates them, and
whoever populates the first corpus must map these ids to real documents. Until that mapping
exists, recall is measuring the harness, not the system.

To make it real:

1. Someone who knows the corpus reads each question and confirms the label is the document
   that actually answers it. Only that person can do this.
2. Add at least one question per stratum. `unanswerable` needs real examples: they are the
   only way to tell a refusal policy from a broken retriever that happens to find nothing.
3. Label `relevant_chunk_ids` where you can afford to. Document-level labels catch
   "retrieved the wrong document"; chunk-level labels catch "retrieved the right document
   but the wrong paragraph", which is the more common failure once chunking lands.

Edit labels in a pull request. Disagreements about a label are worth seeing in a diff, and
this format exists partly so they are.

## `baselines/` — the gate's reference point

`current.json` is written by `make eval-gate` with `--update-baseline`. It records the
metrics **and** the configuration, prompt and model versions that produced them.

That pinning is not housekeeping. `RegressionGate` refuses to compare against a baseline
recorded under different versions, because otherwise a routine embedding-model upgrade reads
as a quality regression and people learn to ignore the gate. When you deliberately change
the model, re-record the baseline as its own reviewed change.

Do not re-record a baseline to make a failing gate go green. The CLI refuses to do it while
the gate is failing; a human can still do it, but it should look deliberate in the history.

## Running

```powershell
make eval        # mini fixture, no gate; reports zeros until a retriever exists
make eval-gate   # golden-v1, enforced against baselines/current.json
```

See `docs/implementation.md` §7 for the metric definitions and the phase in which each one
becomes measurable.