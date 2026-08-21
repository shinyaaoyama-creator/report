import sys
import xml.etree.ElementTree as ET

import yaml


def parse_opml(opml_text: str) -> list[dict]:
    root = ET.fromstring(opml_text)
    body = root.find("body")
    feeds: list[dict] = []

    def _walk(outline, category_hint):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            feeds.append({
                "name": outline.get("text", xml_url),
                "url": xml_url,
                "category_hint": category_hint,
            })
            return

        folder_name = outline.get("text")
        for child in outline.findall("outline"):
            _walk(child, folder_name)

    for outline in body.findall("outline"):
        _walk(outline, None)

    return feeds


def main() -> None:
    opml_path, out_path = sys.argv[1], sys.argv[2]
    with open(opml_path, encoding="utf-8") as f:
        feeds = parse_opml(f.read())
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(feeds, f, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    main()
