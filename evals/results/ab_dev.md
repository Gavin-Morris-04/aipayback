# A/B comparison (dev split)

| Variant | Models | Precision | Recall | F1 (95% CI) | Cost | Extra cost per F1 point |
|---|---|---|---|---|---|---|
| default | claude-haiku-5-5 | 76.2% | 72.7% | 74.4% [54.1%, 88.9%] | $0.0674 | baseline |
| sonnet | claude-haiku-5-5, claude-sonnet-5-5 | 65.2% | 68.2% | 66.7% [46.7%, 81.6%] | $0.2102 | no F1 gain |
