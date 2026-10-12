import os


def test_demo_mode_default():
    os.environ["DEMO_MODE"] = "true"
    from opportunity_radar.config import Settings
    s = Settings(demo_mode=True)
    assert s.demo_mode is True


def test_cv_max_size_bytes():
    from opportunity_radar.config import Settings
    s = Settings(cv_max_size_mb=10)
    assert s.cv_max_size_bytes == 10 * 1024 * 1024


def test_has_llm_no_key():
    from opportunity_radar.config import Settings
    s = Settings(llm_provider="gemini", gemini_api_key="")
    assert s.has_llm is False


def test_has_llm_with_key():
    from opportunity_radar.config import Settings
    s = Settings(llm_provider="gemini", gemini_api_key="test-key-123")
    assert s.has_llm is True


def test_greenhouse_slugs_parsing():
    from opportunity_radar.config import Settings
    s = Settings(greenhouse_board_slugs="company-a,company-b, company-c")
    assert s.greenhouse_slugs_list == ["company-a", "company-b", "company-c"]


def test_greenhouse_slugs_empty():
    from opportunity_radar.config import Settings
    s = Settings(greenhouse_board_slugs="")
    assert s.greenhouse_slugs_list == []
