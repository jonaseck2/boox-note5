from booxctl.ui import find_center

XML = ('<hierarchy><node text="No thanks" bounds="[100,200][300,260]" />'
       '<node content-desc="Install" bounds="[10,20][30,40]" /></hierarchy>')


def test_find_by_text_returns_center():
    assert find_center(XML, "No thanks") == (200, 230)


def test_find_by_content_desc():
    assert find_center(XML, "Install") == (20, 30)


def test_missing_text_returns_none():
    assert find_center(XML, "Continue") is None


def test_find_text_with_xml_entity():
    xml = '<hierarchy><node text="Wallpaper &amp; style" bounds="[0,0][100,40]" /></hierarchy>'
    assert find_center(xml, "Wallpaper & style") == (50, 20)
