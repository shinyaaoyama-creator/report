import textwrap

from scripts.opml_to_feeds import parse_opml


def test_parse_opml_extracts_feeds_with_folder_as_category_hint():
    opml = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
          <body>
            <outline text="seo">
              <outline text="Example Blog" type="rss" xmlUrl="https://example.com/feed.xml"/>
            </outline>
            <outline text="Uncategorized Feed" type="rss" xmlUrl="https://example.org/rss"/>
          </body>
        </opml>
        """)

    result = parse_opml(opml)

    assert {"name": "Example Blog", "url": "https://example.com/feed.xml", "category_hint": "seo"} in result
    assert {"name": "Uncategorized Feed", "url": "https://example.org/rss", "category_hint": None} in result
