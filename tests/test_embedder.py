import embedder


def test_embed_returns_list_of_floats():
    result = embedder.embed(["hello world"])
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], list)
    assert isinstance(result[0][0], float)


def test_embed_dimension_is_384():
    result = embedder.embed(["测试文本"])
    assert len(result[0]) == 384


def test_embed_batch():
    texts = ["文本一", "文本二", "文本三"]
    result = embedder.embed(texts)
    assert len(result) == 3
    assert all(len(v) == 384 for v in result)
