from unittest.mock import Mock

from bs4 import BeautifulSoup
import httpx

from app.client import UrjaPortalClient


def make_client(html: str, path: str) -> UrjaPortalClient:
    client = UrjaPortalClient("https://portal.example")
    client.client.close()
    client.client = Mock()
    client.client.get.return_value = httpx.Response(
        200,
        text=html,
        request=httpx.Request("GET", f"https://portal.example/{path}"),
    )
    return client


def test_login_field_detection_uses_id_and_autocomplete_attributes() -> None:
    form = BeautifulSoup(
        """
        <form action="/login">
            <input id="user_name" type="text" autocomplete="username">
            <input id="pwd" type="password" autocomplete="current-password">
            <input type="submit" value="Log in">
        </form>
        """,
        "html.parser",
    ).find("form")

    assert form is not None
    assert UrjaPortalClient._credential_field(form, ("username", "email", "user", "login"), "username") == "user_name"
    assert UrjaPortalClient._credential_field(form, ("password", "pass"), "password") == "pwd"


def test_meter_detail_parses_nameplate_location_and_hierarchy() -> None:
    html = """
    <section><h2>Nameplate</h2>
      <dl>
        <dt>Meter ID</dt><dd>J100001</dd>
        <dt>Serial No</dt><dd>GE84132</dd>
        <dt>Make</dt><dd>L&amp;T</dd>
        <dt>Phase Type</dt><dd>single</dd>
        <dt>Installation Status</dt><dd>Installed</dd>
        <dt>Installation Type</dt><dd>CT Operated</dd>
      </dl>
    </section>
    <section><h2>Location</h2><p>26.822100, 75.907200</p></section>
    <nav aria-label="breadcrumb">
      <ol><li>Jaipur Zone 2 (Z-02)</li><li>Feeder 1</li><li>DT-002</li></ol>
    </nav>
    """
    client = make_client(html, "meters/J100001")

    assert client.get_meter_details("J100001") == {
        "meter_id": "J100001",
        "serial_no": "GE84132",
        "make": "L&T",
        "phase_type": "single",
        "installation_status": "Installed",
        "installation_type": "CT Operated",
        "dt_id": "DT-002",
        "zone": "Jaipur Zone 2 (Z-02)",
        "location_lat": 26.8221,
        "location_long": 75.9072,
        "full_hierarchy": "Jaipur Zone 2 (Z-02) > Feeder 1 > DT-002",
    }


def test_meter_list_uses_headers_and_decodes_html_entities() -> None:
    html = """
    <table>
      <thead><tr><th>METER</th><th>SERIAL</th><th>MAKE</th>
      <th>PHASE</th><th>STATUS</th><th>DT</th></tr></thead>
      <tbody><tr><td><a href="/meters/J100001">J100001</a></td>
      <td>GE84132</td><td>L&amp;T</td><td>single</td>
      <td>Installed</td><td>DT-002</td></tr></tbody>
    </table>
    """
    client = make_client(html, "meters")

    assert client.list_meters() == [
        {
            "meter_id": "J100001",
            "serial_no": "GE84132",
            "make": "L&T",
            "phase_type": "single",
            "installation_status": "Installed",
            "dt_id": "DT-002",
        }
    ]


def test_consumption_parses_portal_dates_sorts_desc_and_limits() -> None:
    html = """
    <table>
      <thead><tr><th>TIMESTAMP</th><th>KWH</th><th>KVAH</th></tr></thead>
      <tbody>
        <tr><td>23/06/2026 23:30</td><td>42594.05</td><td>46001.58</td></tr>
        <tr><td>23/06/2026 23:00</td><td>42590.05</td><td>45996.58</td></tr>
      </tbody>
    </table>
    """
    client = make_client(html, "meters/J100001")

    assert client.get_consumption("J100001", limit=1) == [
        {
            "timestamp": "2026-06-23T23:30:00",
            "kwh": 42594.05,
            "kvah": 46001.58,
        }
    ]
