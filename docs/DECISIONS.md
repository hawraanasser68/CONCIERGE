# Decisions

## Owner C — Classifier deployment choice

Decision: deploy the classical TF-IDF + logistic regression router from `modelserver/artifacts/classical_model.joblib`.

Why this ships:

- It preserved strong public-test performance (`macro_f1=0.9836`) while producing zero wrong direct routes on both the threshold-selection set and the final product golden set.
- The DL ONNX baseline scored slightly higher on the public test set, but it produced high-confidence wrong direct routes (`2` on public test, `3` on final product golden), which is the more dangerous failure mode for direct routing.
- The classical artifact keeps the serving runtime lean: `sklearn + joblib`, with no `torch`, `transformers`, or `sentence-transformers` in the modelserver container.

Operational consequence:

- The deployed model remains `classical`.
- The DL ONNX artifact stays in-repo as a documented comparison baseline, not as the default serving path.
- The runtime serving threshold is `0.80`. The exported `0.75` threshold is kept only as Colab experiment provenance and does not control modelserver behavior.
- `/embed` remains a 768-zero contract stub because no BGE ONNX artifact was present in the export; it must not be treated as production retrieval quality.
