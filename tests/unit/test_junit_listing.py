"""Console launcher listings captured from real `discover --details=flat` runs (tests/unit/surefire/README.md)."""
from pathlib import Path

import pytest

from corsair.reports.junit_listing import listed

LISTINGS = Path(__file__).with_name('surefire')
WIKI = 'org.apache.wiki.BenchmarkWikiServletForwardingTest'


def test_jupiter_and_vintage_listings_name_class_and_method():
    assert listed((LISTINGS / 'listing-jspwiki.txt').read_bytes()) == (
        (WIKI, 'benignPageKeepsEncodedPageParameter'), (WIKI, 'inertWebRootResourceCannotSelectForwardTarget'))
    assert listed((LISTINGS / 'listing-junit4.txt').read_bytes()) == (
        ('corsair.sample.LegacyTest', 'security'), ('corsair.sample.LegacyTest', 'control'))


JSPWIKI = (LISTINGS / 'listing-jspwiki.txt').read_bytes()


@pytest.mark.parametrize('data', [
    b'', b'\xff' + JSPWIKI, JSPWIKI * 2000,
    JSPWIKI.replace(b'2 tests found', b'3 tests found'),
    JSPWIKI.replace(b'[         2 tests found      ]\n', b''),
    JSPWIKI.replace(b'[method:benignPageKeepsEncodedPageParameter()]', b'[method:benignPageKeepsEncodedPageParameter(int)]'),
    JSPWIKI.replace(b'[class:org.apache.wiki.BenchmarkWikiServletForwardingTest]/[method:benignPage',
                    b'[class:org.apache.wiki.BenchmarkWikiServletForwardingTest]/[nested-class:Inner]/[method:benignPage'),
    JSPWIKI.replace(b'[engine:junit-jupiter]/[class:org.apache.wiki.BenchmarkWikiServletForwardingTest]/[method:benign',
                    b'[engine:other]/[class:org.apache.wiki.BenchmarkWikiServletForwardingTest]/[method:benign'),
])
def test_inexact_listings_are_refused(data):
    assert listed(data) is None
