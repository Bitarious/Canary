from copy import deepcopy

import numpy as np
import pytest

from driftops.tslm_dataset import prepare_input


def raw_input():
    return {"time_series": [[2**40] * 28, list(range(28))],
            "time_series_text": ["smart_5_raw; raw units", "smart_194_raw; raw units"],
            "pre_prompt": "untrusted source prompt", "post_prompt": "untrusted"}


def test_bridge_ignores_targets_and_untrusted_prompt_text():
    raw = raw_input()
    expected = prepare_input(raw)
    raw.update(target="future failure", pre_prompt="future failure", rationale="future failure", failure=1)
    assert prepare_input(raw) == expected
    values = np.array(expected["time_series"])
    assert np.isfinite(values).all()
    assert np.all(values[0] == 0)
    assert np.isclose(values[1].std(ddof=1), 1)


def test_bridge_rejects_missing_nonfinite_and_unknown_channels():
    for damage in ("missing", "nonfinite", "channel"):
        raw = raw_input()
        if damage == "missing":
            raw["time_series"][0].pop()
        elif damage == "nonfinite":
            raw["time_series"][1][5] = float("nan")
        else:
            raw["time_series_text"][0] = "recorded_failure"
        with pytest.raises(ValueError):
            prepare_input(raw)


def test_invalid_generated_answers_receive_zero_credit():
    pytest.importorskip("torch")
    from driftops.evaluate_tslm import metrics
    examples = [{"inputs": prepare_input(raw_input()),
                 "target": "smart_5_raw: constant; smart_194_raw: rising."}]
    for output in ("smart_5_raw: constant.", "smart_5_raw: constant; smart_194_raw: rising. Replace this drive.",
                   "smart_5_raw: constant; smart_194_raw: rising; failure: yes."):
        result = metrics(examples, [output])
        assert result["invalid_outputs"] == 1
        assert result["channel_accuracy"] == 0
    assert metrics(examples, [examples[0]["target"]])["channel_accuracy"] == 1


def test_answer_loss_masks_prompt_and_padding_without_answer_bos():
    torch = pytest.importorskip("torch")
    from types import SimpleNamespace
    from driftops.opentslm import training_tensors

    class Tokenizer:
        eos_token_id = 9

        def __call__(self, text, add_special_tokens, return_tensors):
            assert add_special_tokens is False
            return SimpleNamespace(input_ids=torch.tensor([[int(x) for x in text.split()]]))

    class Model:
        device = "cpu"
        tokenizer = Tokenizer()
        llm = SimpleNamespace(get_input_embeddings=lambda: torch.nn.Embedding(10, 3))

        def pad_and_apply_batch(self, batch):
            return torch.ones(2, 4, 3), torch.tensor([[1, 1, 1, 1], [1, 1, 0, 0]])

    examples = [{"inputs": prepare_input(raw_input()), "target": "1 2 3"},
                {"inputs": prepare_input(raw_input()), "target": "4"}]
    _, attention, labels = training_tensors(Model(), examples)
    assert labels.tolist() == [[-100, -100, -100, -100, 1, 2, 3, 9],
                               [-100, -100, 4, 9, -100, -100, -100, -100]]
    assert attention.tolist() == [[1] * 8, [1, 1, 1, 1, 0, 0, 0, 0]]


def test_structured_grammar_does_not_select_patterns_from_targets():
    pytest.importorskip("torch")
    from types import SimpleNamespace
    from driftops.structured_tslm import answer_trie

    class Tokenizer:
        eos_token_id = 999

        def __call__(self, texts, add_special_tokens):
            return SimpleNamespace(input_ids=[[ord(char) for char in text] for text in texts])

    trie = answer_trie(Tokenizer(), ["smart_5_raw", "smart_194_raw"])
    # The grammar must allow every pattern, even an implausible pattern pair.
    for text in ["smart_5_raw: rising; smart_194_raw: falling.",
                 "smart_5_raw: falling; smart_194_raw: counter reset or decrease.",
                 "smart_5_raw: constant; smart_194_raw: constant."]:
        node = trie
        for token in [*[ord(char) for char in text], 999]:
            node = node[token]
        assert node == {}
