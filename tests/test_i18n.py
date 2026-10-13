from dpi_dashboard.i18n import STRINGS, Translator


def test_languages_have_the_same_keys():
    assert STRINGS["en"].keys() == STRINGS["tr"].keys()


def test_explicit_language_and_fallback():
    assert Translator("tr")("on") == "AÇIK"
    assert Translator("xx")("on") == "ON"
    assert "zapret" in Translator("en")("not_installed", service="zapret")
