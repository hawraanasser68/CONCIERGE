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
- `onnxruntime` is included in `modelserver/pyproject.toml` to support the exported DL ONNX baseline and future switchability, while the deployed runtime path remains classical.
- The runtime serving threshold is `0.80`. The exported `0.75` threshold is kept only as Colab experiment provenance and does not control modelserver behavior.
- `/embed` remains a 768-zero contract stub because no BGE ONNX artifact was present in the export; it must not be treated as production retrieval quality.

## Owner C — Classifier artifact commit policy

Decision: commit the small SHA-pinned classifier artifacts required by the modelserver for bootcamp reproducibility and fresh-clone demo readiness.

The original Owner C spec assumed artifacts would be mounted or ignored. For this repo branch, the exception is intentional: `classical_model.joblib`, the exported DL ONNX baseline, and their small auxiliary runtime artifacts remain committed with hashes recorded in `modelserver/model_card.yaml`.

Raw datasets, Colab export folders, caches, zip files, notebooks caches, secrets, and large/generated artifacts remain ignored and must not be committed.
