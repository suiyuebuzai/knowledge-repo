from ingest import SUPPORTED, FIND_SUPPORTED


def test_supported_includes_all_new_formats():
    for ext in (".md", ".xlsx", ".xls", ".pptx", ".csv", ".html", ".htm"):
        assert ext in SUPPORTED, f"Missing {ext} in SUPPORTED"


def test_find_supported_equals_supported():
    assert SUPPORTED == FIND_SUPPORTED, "FIND_SUPPORTED must equal SUPPORTED"
