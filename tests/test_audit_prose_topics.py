"""The normalized topic key that sits beside the as-reported heading path.

Each case is a caption measured in the corpus, not an invented one.
"""
from src.audit_reports.prose import _fold
from src.audit_reports.prose_topics import BY_SLUG, TOPICS, topic_of


def t(heading: str) -> str | None:
    return topic_of(heading, _fold)


def test_punctuation_does_not_block_a_match():
    """'kâr/zarara yansıtılan' never matches a keyword written 'KAR ZARARA
    YANSITILAN' unless punctuation is flattened — that omission alone lost 51
    FVPL headings."""
    assert t("Gerçeğe uygun değer farkı kar/zarara yansıtılan finansal varlıklar") \
        == "fvpl_assets"


def test_the_specific_caption_wins_over_the_general_one():
    """The FVOCI and FVPL captions share their opening words; testing the
    general rule first swallows the specific one."""
    assert t("Gerçeğe uygun değer farkı diğer kapsamlı gelire yansıtılan "
             "finansal varlıklara ilişkin bilgiler") == "fvoci_assets"
    assert t("Fair value through other comprehensive income financial assets") \
        == "fvoci_assets"


def test_turkish_and_english_captions_reach_the_same_topic():
    """32% of filings are English convenience translations; a topic that only
    speaks Turkish silently splits every disclosure in two."""
    for tr, en in [
        ("Mevduata ilişkin bilgiler", "Information on deposits"),
        ("Satış amaçlı elde tutulan duran varlıklar",
         "Assets held for sale and discontinued operations"),
        ("Türev finansal araçlara ilişkin açıklamalar",
         "Explanations on derivative instruments"),
        ("Özkaynaklara ilişkin bilgiler", "Information on shareholders equity"),
    ]:
        assert t(tr) is not None and t(tr) == t(en), (tr, en, t(tr), t(en))


def test_unmatched_caption_returns_none_rather_than_guessing():
    assert t("Bu bölümde yer alan hususlar hakkında ek bilgi bulunmamaktadır") is None
    assert t("") is None
    assert t(None) is None


def test_every_topic_is_reachable_and_unique():
    slugs = [x.slug for x in TOPICS]
    assert len(slugs) == len(set(slugs))
    assert set(BY_SLUG) == set(slugs)
    for x in TOPICS:
        assert x.keywords and x.label_en and x.label_tr and x.group
        # Keywords are pre-folded: uppercase ASCII, no punctuation to match on.
        for k in x.keywords:
            assert k == k.upper() and k.isascii(), (x.slug, k)
