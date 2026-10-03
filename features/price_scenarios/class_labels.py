"""Resolve issuer QName labels from captured XSD/linkbase documents, without IO."""
from bs4 import BeautifulSoup


def official_labels(markup, xsd, linkbase):
    html, schema, labels = (BeautifulSoup(text, parser) for text, parser in
                            ((markup, "html.parser"), (xsd, "xml"), (linkbase, "xml")))
    root = schema.find("schema")
    namespace = root.get("targetNamespace") if root else None
    prefixes = {key.removeprefix("xmlns:") for tag in html.find_all(True) for key, value in tag.attrs.items()
                if key.startswith("xmlns:") and value == namespace}
    if len(prefixes) != 1:
        return {}
    prefix = next(iter(prefixes))
    elements = {tag.get("id"): prefix + ":" + tag["name"] for tag in schema.find_all("element") if tag.get("id") and tag.get("name")}
    output = {}
    for section in labels.find_all("labelLink"):
        locs = {t.get("xlink:label"): elements.get(t.get("xlink:href", "").split("#")[-1]) for t in section.find_all("loc")}
        texts = {t.get("xlink:label"): t.get_text(strip=True) for t in section.find_all("label")
                 if t.get("xml:lang", "").lower() in {"en", "en-us"} and t.get("xlink:role") == "http://www.xbrl.org/2003/role/label"}
        for arc in section.find_all("labelArc"):
            member, text = locs.get(arc.get("xlink:from")), texts.get(arc.get("xlink:to"))
            if member and text:
                output.setdefault(member, []).append(text)
    return output
