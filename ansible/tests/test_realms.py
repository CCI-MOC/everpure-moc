"""Sanity checks for ansible/group_vars/all/realms.yaml."""

import ipaddress
import itertools
import re
from pathlib import Path

import pytest
import yaml

REALMS_FILE = Path(__file__).parent.parent / "group_vars" / "all" / "realms.yaml"
REQUIRED = {
    "name",
    "interface_address",
    "s3_endpoint",
    "subnet_prefix",
    "subnet_vlan",
    "subnet_gateway",
    "dns_domain",
    "dns_nameservers",
}
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
HOSTNAME_RE = re.compile(r"^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")

REALMS = yaml.safe_load(REALMS_FILE.read_text())["realms"]
IDS = [r.get("name", f"index-{i}") for i, r in enumerate(REALMS)]


def net(realm):
    return ipaddress.ip_network(realm["subnet_prefix"], strict=True)


@pytest.mark.parametrize("realm", REALMS, ids=IDS)
class TestRealm:
    def test_required_keys(self, realm):
        assert REQUIRED <= realm.keys(), f"missing: {REQUIRED - realm.keys()}"

    def test_name(self, realm):
        assert NAME_RE.match(realm["name"]), "lowercase alphanumerics and '-' only"

    def test_subnet_has_no_host_bits(self, realm):
        net(realm)  # strict=True raises on e.g. 10.0.0.5/24

    def test_vlan_range(self, realm):
        vlan = realm["subnet_vlan"]
        assert isinstance(vlan, int) and 1 <= vlan <= 4094, "invalid vlan_id"

    def test_addresses_in_subnet(self, realm):
        n = net(realm)
        addrs = {
            "interface_address": realm["interface_address"],
            "subnet_gateway": realm["subnet_gateway"],
        }
        for i, dns in enumerate(realm["dns_nameservers"]):
            addrs[f"dns_nameservers[{i}]"] = dns
        for label, value in addrs.items():
            ip = ipaddress.ip_address(value)
            assert ip in n, f"{label} {ip} not in {n}"
            assert ip not in (n.network_address, n.broadcast_address), (
                f"{label} {ip} is the network/broadcast address"
            )

    def test_interface_not_gateway_or_dns(self, realm):
        ip = realm["interface_address"]
        assert ip != realm["subnet_gateway"], "Interface address cannot be network gateway"
        assert ip not in realm["dns_nameservers"], "Interface address and DNS address cannot be same"

    def test_dns_nameservers_nonempty_and_unique(self, realm):
        ns = realm["dns_nameservers"]
        assert isinstance(ns, list) and ns and len(ns) == len(set(ns))

    def test_hostnames(self, realm):
        assert HOSTNAME_RE.match(realm["s3_endpoint"]), realm["s3_endpoint"]
        assert HOSTNAME_RE.match(realm["dns_domain"]), realm["dns_domain"]


@pytest.mark.parametrize("key", ["name", "subnet_vlan", "interface_address", "s3_endpoint"])
def test_unique(key):
    values = [r[key] for r in REALMS]
    dupes = {v for v in values if values.count(v) > 1}
    assert not dupes, f"duplicate {key}: {dupes}"


def test_subnets_do_not_overlap():
    for a, b in itertools.combinations(REALMS, 2):
        assert not net(a).overlaps(net(b)), (
            f"{a['name']} ({net(a)}) overlaps {b['name']} ({net(b)})"
        )
