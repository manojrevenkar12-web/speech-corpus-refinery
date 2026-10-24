"""Rights: robots.txt (RFC 9309), TDMRep, licence normalisation and policy."""

import pytest

from scr import config
from scr.rights import licence, robots, tdmrep

RFC_EXAMPLE = """
User-Agent: *
Disallow: *.gif$
Disallow: /example/
Allow: /publications/

User-Agent: foobot
Disallow:/
Allow:/example/page.html
Allow:/example/allowed.gif

User-Agent: barbot
User-Agent: bazbot
Disallow: /example/page.html

User-Agent: quxbot
"""


@pytest.mark.parametrize(
    ("agent", "path", "ok"),
    [
        ("foobot", "/example/page.html", True),
        ("foobot", "/example/allowed.gif", True),
        ("foobot", "/other.html", False),
        ("FooBot", "/example/page.html", True),  # product tokens match case-insensitively
        ("barbot", "/example/page.html", False),
        ("bazbot", "/example/page.html", False),
        ("barbot", "/example/other.html", True),  # barbot's own group, not *
        ("quxbot", "/anything", True),  # an empty group allows everything
        ("otherbot", "/picture.gif", False),
        ("otherbot", "/picture.gif?x=1", True),  # $ anchors the end of the path
        ("otherbot", "/example/x", False),
        ("otherbot", "/publications/x", True),
        ("otherbot", "/robots.txt", True),
    ],
)
def test_rfc9309_example(agent, path, ok):
    assert robots.parse(RFC_EXAMPLE).allowed(f"https://example.com{path}", agent) is ok


def test_longest_match_wins_and_allow_wins_ties():
    r = robots.parse("User-agent: *\nDisallow: /recordings/\nAllow: /recordings/public/\nDisallow: /tie\nAllow: /tie\n")
    assert not r.allowed("http://h/recordings/members/a.flac", "ScrBot")
    assert r.allowed("http://h/recordings/public/a.flac", "ScrBot")
    assert r.allowed("http://h/tie", "ScrBot")


def test_groups_for_the_same_agent_merge_and_star_is_only_a_fallback():
    text = "User-agent: ScrBot\nDisallow: /a/\n\nUser-agent: *\nDisallow: /\n\nUser-agent: scrbot\nDisallow: /b/\nCrawl-delay: 3\n"
    r = robots.parse(text)
    assert not r.allowed("http://h/a/x", "ScrBot") and not r.allowed("http://h/b/x", "ScrBot")
    assert r.allowed("http://h/c/x", "ScrBot")
    assert r.crawl_delay("ScrBot") == 3.0


def test_percent_encoding_and_empty_disallow():
    r = robots.parse("User-agent: *\nDisallow: /path%20with\nDisallow:\n")
    assert not r.allowed("http://h/path%20with/x", "a") and not r.allowed("http://h/path with/x", "a")
    assert r.allowed("http://h/other", "a")


@pytest.mark.parametrize(("status", "allowed"), [(200, True), (404, True), (403, True), (500, False), (503, False), (None, False)])
def test_fetch_outcomes(status, allowed):
    assert robots.from_response(status, "").allowed("http://h/x", "ScrBot") is allowed


def test_tdmrep_file_header_meta_precedence():
    rules = tdmrep.parse_file(
        '[{"location": "/studio/*", "tdm-reservation": 1, "tdm-policy": "https://h/p.json"}, {"location": "/open/", "tdm-reservation": 0}]'
    )
    r = tdmrep.from_file(rules, "http://h/studio/take1.flac")
    assert r.reserved is True and r.policy == "https://h/p.json" and r.where == "file"
    assert tdmrep.from_file(rules, "http://h/open/take4.flac").reserved is False
    assert tdmrep.from_file(rules, "http://h/elsewhere").reserved is None
    # a header overrides the file, a meta tag overrides both
    r2 = tdmrep.from_headers({"TDM-Reservation": "0"}, r)
    assert r2.reserved is False and r2.where == "header"
    r3 = tdmrep.from_html('<head><meta name="tdm-reservation" content="1"></head>', r2)
    assert r3.reserved is True and r3.where == "meta"
    # protocol errors count as unset
    assert tdmrep.from_headers({"tdm-reservation": "yes"}, tdmrep.Reservation(None)).reserved is None
    assert tdmrep.parse_file("not json") == [] and tdmrep.parse_file('{"location": "/"}') == []


@pytest.mark.parametrize(
    ("raw", "spdx"),
    [
        ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
        ("http://creativecommons.org/licenses/by-nc/3.0/deed.de", "CC-BY-NC-3.0"),
        ("https://creativecommons.org/licenses/by-sa/4.0/legalcode", "CC-BY-SA-4.0"),
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
        ("https://creativecommons.org/publicdomain/mark/1.0/", "CC-PDM-1.0"),
        ("cc-by-4.0", "CC-BY-4.0"),
        ("cc0-1.0", "CC0-1.0"),
        ("CC-BY-NC-ND-4.0", "CC-BY-NC-ND-4.0"),
        ("Public Domain", "LicenseRef-PublicDomain"),
        ("© 2024 All Rights Reserved", "LicenseRef-AllRightsReserved"),
        ("", licence.UNKNOWN),
        ("free to use!", licence.UNKNOWN),
    ],
)
def test_normalise(raw, spdx):
    assert licence.normalise(raw) == spdx


def test_policy():
    pol = config.rights()
    assert licence.decide("CC-BY-4.0", pol).allowed and licence.decide("CC-BY-4.0", pol).attribution
    assert licence.decide("CC-BY-SA-4.0", pol).share_alike
    v = licence.decide("CC-BY-NC-4.0", pol)
    assert not v.allowed and "non-commercial" in v.reason
    assert not licence.decide(licence.UNKNOWN, pol).allowed
    assert licence.blocked_domain("pirate.example", pol) and licence.blocked_domain("cdn.pirate.example", pol)
    assert not licence.blocked_domain("notpirate.example", pol)
