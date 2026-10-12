"""Client address for rate limiting: X-Forwarded-For is trusted only from a trusted peer."""

import pytest

from config import settings as settings_module
from services.rate_limit.client_ip import client_address, parse_trusted_networks

GATEWAY = "10.218.10.5"
TRUSTED = parse_trusted_networks(["10.218.10.0/24"])


def test_untrusted_peer_ignores_forwarded_for_completely():
    assert client_address("198.51.100.7", "1.2.3.4", TRUSTED) == "198.51.100.7"
    assert client_address("198.51.100.7", "9.9.9.9, 1.2.3.4", TRUSTED) == "198.51.100.7"


def test_trusted_peer_uses_the_right_most_untrusted_hop():
    assert client_address(GATEWAY, "1.2.3.4", TRUSTED) == "1.2.3.4"
    assert client_address(GATEWAY, "1.2.3.4, 10.218.10.9", TRUSTED) == "1.2.3.4"


def test_a_spoofed_left_most_value_is_ignored_when_the_proxy_appends_the_real_client():
    # The client sent 6.6.6.6 itself. The gateway appended the address it saw.
    assert client_address(GATEWAY, "6.6.6.6, 1.2.3.4", TRUSTED) == "1.2.3.4"
    assert client_address(GATEWAY, "6.6.6.6, 7.7.7.7, 1.2.3.4", TRUSTED) == "1.2.3.4"


@pytest.mark.parametrize("header", [
    "not-an-ip",
    "1.2.3.4, not-an-ip",
    "1.2.3.4:8080",
    "1.2.3.4,,5.6.7.8",
    "",
])
def test_malformed_or_empty_header_falls_back_to_the_direct_peer(header):
    assert client_address(GATEWAY, header, TRUSTED) == GATEWAY


def test_missing_header_uses_the_direct_peer():
    assert client_address(GATEWAY, None, TRUSTED) == GATEWAY


def test_without_trusted_networks_the_header_is_never_honored():
    assert client_address(GATEWAY, "1.2.3.4", ()) == GATEWAY


def test_when_every_hop_is_a_trusted_proxy_the_left_most_is_used():
    assert client_address(GATEWAY, "10.218.10.8, 10.218.10.9", TRUSTED) == "10.218.10.8"


def test_an_ipv4_mapped_ipv6_peer_is_treated_as_the_ipv4_peer():
    assert client_address("::ffff:10.218.10.5", "1.2.3.4", TRUSTED) == "1.2.3.4"
    assert client_address("::ffff:198.51.100.7", "1.2.3.4", TRUSTED) == "198.51.100.7"


def test_ipv6_clients_are_supported_behind_a_trusted_ipv6_proxy():
    trusted = parse_trusted_networks(["2001:db8:10::/48"])
    assert client_address("2001:db8:10::5", "2001:db8:99::20", trusted) == "2001:db8:99::20"


def test_an_ipv6_peer_is_not_trusted_by_an_ipv4_network():
    assert client_address("2001:db8::5", "1.2.3.4", TRUSTED) == "2001:db8::5"


def test_missing_or_unparseable_peer_yields_a_stable_label():
    assert client_address(None, None, TRUSTED) == "unknown"
    assert client_address("testclient", None, TRUSTED) == "testclient"


def test_parse_trusted_networks_skips_blank_entries_and_rejects_invalid_ones():
    networks = parse_trusted_networks([" 10.0.0.0/8 ", "", "  "])
    assert [str(network) for network in networks] == ["10.0.0.0/8"]
    with pytest.raises(ValueError):
        parse_trusted_networks(["not-a-network"])


def test_settings_reject_an_invalid_trusted_proxy_network():
    with pytest.raises(ValueError, match="PMS_TRUSTED_PROXY_CIDRS"):
        settings_module._trusted_proxy_networks("10.0.0.0/8, not-a-network")
    assert settings_module._trusted_proxy_networks(" 10.0.0.0/8 , 192.168.1.0/24 ") == ("10.0.0.0/8", "192.168.1.0/24")


def test_positive_integer_settings_must_be_greater_than_zero(monkeypatch):
    monkeypatch.setenv("PMS_RATE_LIMIT_TEST_VALUE", "0")
    with pytest.raises(ValueError, match="PMS_RATE_LIMIT_TEST_VALUE must be greater than zero"):
        settings_module._positive_int_setting("PMS_RATE_LIMIT_TEST_VALUE", 10)
    monkeypatch.setenv("PMS_RATE_LIMIT_TEST_VALUE", "-3")
    with pytest.raises(ValueError):
        settings_module._positive_int_setting("PMS_RATE_LIMIT_TEST_VALUE", 10)
    monkeypatch.setenv("PMS_RATE_LIMIT_TEST_VALUE", "25")
    assert settings_module._positive_int_setting("PMS_RATE_LIMIT_TEST_VALUE", 10) == 25
    monkeypatch.delenv("PMS_RATE_LIMIT_TEST_VALUE")
    assert settings_module._positive_int_setting("PMS_RATE_LIMIT_TEST_VALUE", 10) == 10
