#!/usr/bin/env python3
"""
Realm isolation test for a FlashBlade.

Uses two realms set up by ansible/flashblade-realm.yaml (realm A and
realm B) and shows that they cannot see or reach each other:

  1. A file system exported by a realm's NFS server shows up in
     `showmount -e` against that realm's VIP, and does not show up against
     the other realm's VIP.
  2. Through a realm's VIP, a client can mount that realm's export but not
     the other realm's, over NFSv3 and NFSv4.1. The test exports allow any
     client, so the client's IP address plays no part in this.
  3. A realm's API token cannot see the other realm's file systems.
  4. A realm's API token cannot put a network interface on the other
     realm's subnet, and cannot give its realm access to that subnet.

At the end it deletes the test file systems, exports and export policies it
created.

Usage:
    export REALM_A_API_TOKEN=...
    export REALM_B_API_TOKEN=...
    python3 realm_isolation_test.py config.ini

See README.md for details.
"""

import configparser
import datetime
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

import requests
import urllib3

API = "/api/2.22"

# Objects created by ansible/flashblade-realm.yaml for each realm
# (names from ansible/roles/flashblade_realm/defaults/main.yml).
SERVER = "nfs-server"
INTERFACE = "interface"
DNS = "dns"

# Objects this script creates in each realm.
TEST_FS = "isolation-test-fs"
TEST_POLICY = "isolation-test-policy"
PROBE_SERVER = "isolation-probe-server"
PROBE_VIP_OTHER = "isolation-probe-other-subnet"
PROBE_VIP_OWN = "isolation-probe-own-subnet"

results = []  # (PASS/FAIL/INFO, description)
leftovers = []  # probe servers/VIPs a realm token was (unexpectedly) allowed to create
cleanup_problems = []  # test objects that could not be deleted


def heading(title):
    print("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78)


def indent(text):
    return textwrap.indent(text.rstrip(), "    ")


def record(result, description):
    print(f"\n>>> {result}: {description}")
    results.append((result, description))


def check(passed, description):
    record("PASS" if passed else "FAIL", description)


def items(response):
    if response.status_code != 200:
        return []
    return response.json().get("items", [])


def error_text(response):
    try:
        errors = response.json().get("errors", [])
    except ValueError:
        return response.text
    messages = [f"{e.get('message', '')} {e.get('context', '')}".strip() for e in errors]
    return "; ".join(messages) or response.text


def not_permitted(response):
    """True if the FlashBlade refused the request for lack of permission.
    It answers such requests with HTTP 400 and "Operation not permitted."
    Any other error (a bad request, an address in use, ...) does not show
    that a permission boundary was hit, so it does not count as a PASS."""
    return response.status_code != 200 and "Operation not permitted" in response.text


def created_or_exists(response):
    return response.status_code == 200 or "already exists" in response.text


def export_name(realm_name):
    return f"isolation-test-{realm_name}"


class FlashBlade:
    """A REST API session logged in with one realm's API token."""

    def __init__(self, url, token, verify, label):
        self.base = f"https://{url}"
        self.label = label
        self.session = requests.Session()
        self.session.verify = verify
        r = self.session.post(f"{self.base}/api/login", headers={"api-token": token})
        if r.status_code != 200:
            sys.exit(f"Login with the {label} token failed: HTTP {r.status_code} {r.text}")
        self.session.headers["x-auth-token"] = r.headers["x-auth-token"]

    def call(self, method, path, params=None, body=None):
        print(f"\n[{self.label} token] {method} {API}{path}")
        if params:
            print(f"    params: {params}")
        if body is not None:
            print(f"    body:   {json.dumps(body)}")
        r = self.session.request(method, f"{self.base}{API}{path}", params=params, json=body)
        print(f"  -> HTTP {r.status_code}")
        if method == "GET" and r.status_code == 200:
            # Successful lookups only matter for which objects came back,
            # so print their names rather than every field.
            names = [i.get("name") for i in items(r)]
            print(f"    {len(names)} item(s): {names}")
            return r
        try:
            print(indent(json.dumps(r.json(), indent=2)))
        except ValueError:
            print(indent(r.text))
        return r


def run(cmd):
    """Run a command, print it and its output, and return the result (or
    None if it did not finish within 3 minutes)."""
    print("\n$ " + " ".join(cmd))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        print("    timed out after 180 seconds")
        return None
    if (p.stdout + p.stderr).strip():
        print(indent(p.stdout + p.stderr))
    print(f"    (exit status {p.returncode})")
    return p


def showmount(vip):
    """Return the export paths (without the leading /) that `showmount -e`
    lists for the VIP, or None if showmount failed."""
    p = run(["showmount", "-e", vip])
    if p is None or p.returncode != 0:
        return None
    # The first line is a header ("Exports list on <vip>:"); each line after
    # it is "<path> <allowed clients>".
    lines = p.stdout.splitlines()[1:]
    return [line.split()[0].lstrip("/") for line in lines if line.strip()]


def mount_works(vip, export, version):
    """Try to mount vip:/export over the given NFS version, and unmount it
    again if that worked. Returns True if the mount worked."""
    mountpoint = tempfile.mkdtemp(prefix="realm-isolation-")
    # Linux needs root to mount; macOS lets a user mount on a directory
    # they own.
    sudo = [] if os.geteuid() == 0 or sys.platform == "darwin" else ["sudo"]
    p = run(sudo + ["mount", "-t", "nfs", "-o", f"vers={version}",
                    f"{vip}:/{export}", mountpoint])
    worked = p is not None and p.returncode == 0
    if worked:
        u = run(sudo + ["umount", mountpoint])
        if u is None or u.returncode != 0:
            cleanup_problems.append(f"local mount {mountpoint}: could not unmount")
            return worked
    os.rmdir(mountpoint)
    return worked


def main():
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} CONFIG_FILE")
    if not shutil.which("showmount"):
        sys.exit("showmount is not installed (package nfs-utils or nfs-common)")

    config = configparser.ConfigParser()
    if not config.read(sys.argv[1]):
        sys.exit(f"Cannot read config file {sys.argv[1]}")
    url = config["flashblade"]["url"]
    verify = config["flashblade"].getboolean("verify_tls", True)
    if not verify:
        urllib3.disable_warnings()
    versions = config.get("nfs", "mount_versions", fallback="3, 4.1")
    nfs_versions = [v.strip() for v in versions.split(",") if v.strip()]

    realms = []
    for section, token_var in (("realm_a", "REALM_A_API_TOKEN"), ("realm_b", "REALM_B_API_TOKEN")):
        token = os.environ.get(token_var)
        if not token:
            sys.exit(f"{token_var} is not set")
        name = config[section]["name"]
        realms.append({
            "name": name,
            "spare_ip": config[section]["spare_ip"],
            "fb": FlashBlade(url, token, verify, name),
        })
    a, b = realms
    if a["name"] == b["name"]:
        sys.exit("realm_a and realm_b must be different realms")
    pairs = [(a, b), (b, a)]

    heading("Realm isolation test")
    print(f"Started:    {datetime.datetime.now().astimezone().isoformat(timespec='seconds')}")
    print(f"FlashBlade: {url}")
    r = a["fb"].call("GET", "/arrays")
    if items(r):
        array = items(r)[0]
        print(f"\nArray: {array.get('name')}, {array.get('os')} {array.get('version')}")
    print(f"Realm A:    {a['name']}\nRealm B:    {b['name']}")
    print(f"NFS versions to mount with: {', '.join(nfs_versions) or 'none'}")

    # ------------------------------------------------------------------
    heading("Preflight: look up each realm's NFS VIP and subnet")
    for realm in realms:
        fb, name = realm["fb"], realm["name"]

        r = fb.call("GET", "/network-interfaces", {"names": f"{name}::{INTERFACE}"})
        if not items(r):
            sys.exit(f"Cannot find {name}::{INTERFACE}. Was the realm set up with flashblade-realm.yaml?")
        realm["vip"] = items(r)[0]["address"]

        r = fb.call("GET", "/subnets", {"names": f"{name}-subnet"})
        if not items(r):
            sys.exit(f"Cannot read {name}-subnet with the {name} token.")
        subnet = ipaddress.ip_network(items(r)[0]["prefix"])

        # The spare IP is used to try to create interfaces. It has to be in
        # the realm's subnet and unused, or a rejection would mean nothing.
        if ipaddress.ip_address(realm["spare_ip"]) not in subnet:
            sys.exit(f"spare_ip {realm['spare_ip']} for {name} is not in {name}-subnet ({subnet})")
        r = fb.call("GET", "/network-interfaces")
        if realm["spare_ip"] in [i["address"] for i in items(r)]:
            sys.exit(f"spare_ip {realm['spare_ip']} is already used by an interface. "
                     "If this is from an earlier run, clean up first.")

        print(f"\n{name}: VIP {realm['vip']}, subnet {subnet}, spare IP {realm['spare_ip']}")

    # Cleanup runs even if a check crashes, so the next run starts clean.
    try:
        run_tests(realms, pairs, nfs_versions)
    finally:
        cleanup(realms)
    print_summary()


def run_tests(realms, pairs, nfs_versions):
    """Create the test file systems and exports, then run the checks."""
    # ------------------------------------------------------------------
    heading("Setup: create a file system in each realm and export it on the realm's NFS server")
    for realm in realms:
        fb, name = realm["fb"], realm["name"]
        fs = f"{name}::{TEST_FS}"
        policy = f"{name}::{TEST_POLICY}"

        # The realm's own export policy only lets clients on the realm's
        # subnet mount. The test exports use a policy that lets ANY client
        # mount instead, so that the client's IP address plays no part in
        # the checks: if a mount fails, it is not because of the client.
        r = fb.call("POST", "/nfs-export-policies", {"names": policy},
                    {"rules": [{"client": "*", "access": "no-squash", "permission": "rw",
                                "required_transport_security": "none"}]})
        if not created_or_exists(r):
            sys.exit(f"Could not create {policy}: {error_text(r)}")

        # A file system in a realm cannot have the array's "default exports"
        # ("Default exports cannot be created in realms"). default_exports
        # turns them off; the API expects the literal string '' (two single
        # quotes) for "none". Both NFSv3 (which RDMA clients use) and
        # NFSv4.1 are enabled, so both can be tested.
        r = fb.call("POST", "/file-systems", {"names": fs, "default_exports": "''"},
                    {"provisioned": 1024**3, "nfs": {"v3_enabled": True, "v4_1_enabled": True}})
        if not created_or_exists(r):
            sys.exit(f"Could not create {fs}: {error_text(r)}")

        r = fb.call("POST", "/file-system-exports",
                    {"member_names": fs, "policy_names": policy},
                    {"export_name": export_name(name), "server": {"name": f"{name}::{SERVER}"}})
        if not created_or_exists(r):
            sys.exit(f"Could not export {fs}: {error_text(r)}")

    # ------------------------------------------------------------------
    heading("Check 1: showmount -e against each realm's NFS VIP")
    for realm, other in pairs:
        exports = showmount(realm["vip"])
        own, theirs = export_name(realm["name"]), export_name(other["name"])
        check(exports is not None and own in exports,
              f"showmount -e {realm['vip']} ({realm['name']} VIP) lists {realm['name']}'s export /{own}")
        check(exports is not None and theirs not in exports,
              f"showmount -e {realm['vip']} ({realm['name']} VIP) does not list {other['name']}'s export /{theirs}")

    # ------------------------------------------------------------------
    heading("Check 2: mount each realm's export, and the other realm's, through the realm's VIP")
    if not nfs_versions:
        record("INFO", "Mount checks skipped: mount_versions is empty in the config")
    for realm, other in pairs:
        vip = realm["vip"]
        own, theirs = export_name(realm["name"]), export_name(other["name"])
        for version in nfs_versions:
            own_ok = mount_works(vip, own, version)
            check(own_ok,
                  f"NFSv{version}: {vip}:/{own} ({realm['name']}'s own export) can be mounted")
            # This only means something if the mount above worked: then the
            # VIP, the NFS version and the client are all fine, and the
            # export policy lets any client in, so a failure here can only
            # mean the server does not have the other realm's export.
            other_ok = mount_works(vip, theirs, version)
            check(own_ok and not other_ok,
                  f"NFSv{version}: {vip}:/{theirs} ({other['name']}'s export, through "
                  f"{realm['name']}'s VIP) cannot be mounted")

    # ------------------------------------------------------------------
    heading("Check 3: each realm's token cannot see the other realm's file systems")
    for realm, other in pairs:
        fb, name, other_name = realm["fb"], realm["name"], other["name"]

        r = fb.call("GET", "/file-systems")
        names = [i["name"] for i in items(r)]
        check(f"{name}::{TEST_FS}" in names,
              f"{name} token lists its own file system {name}::{TEST_FS}")
        seen = [n for n in names if n.startswith(f"{other_name}::")]
        check(r.status_code == 200 and not seen,
              f"{name} token lists none of {other_name}'s file systems"
              + (f" (it listed: {seen})" if seen else ""))

        r = fb.call("GET", "/file-systems", {"names": f"{other_name}::{TEST_FS}"})
        check(not items(r),
              f"{name} token cannot look up {other_name}::{TEST_FS} by name "
              f"(HTTP {r.status_code}: {error_text(r)})")

    # ------------------------------------------------------------------
    heading("Info: subnets each realm's token can list")
    for realm, other in pairs:
        r = realm["fb"].call("GET", "/subnets")
        names = [i["name"] for i in items(r)]
        listed = "is" if f"{other['name']}-subnet" in names else "is not"
        record("INFO", f"{realm['name']} token can list subnets {names}; "
                       f"{other['name']}-subnet {listed} among them")

    # ------------------------------------------------------------------
    heading("Check 4: each realm's token cannot attach its realm to the other realm's subnet")

    # An extra server in each realm, so the attempts below are made against a
    # server that nothing is using. If the token is not allowed to create
    # servers, the attempts use the realm's NFS server instead.
    for realm in realms:
        fb, name = realm["fb"], realm["name"]
        probe = f"{name}::{PROBE_SERVER}"
        r = fb.call("POST", "/servers", {"names": probe, "create_ds": f"{probe}_nfs"},
                    {"dns": [{"name": f"{name}::{DNS}"}]})
        if created_or_exists(r):
            realm["server"] = probe
            leftovers.append(f"server {probe}")
            record("INFO", f"{name} token was allowed to create the extra server {probe}")
        else:
            realm["server"] = f"{name}::{SERVER}"
            record("INFO", f"{name} token was not allowed to create a server "
                           f"({error_text(r)}); using {realm['server']} instead")

    for realm, other in pairs:
        fb, name, other_name = realm["fb"], realm["name"], other["name"]

        vip = f"{name}::{PROBE_VIP_OTHER}"
        r = fb.call("POST", "/network-interfaces", {"names": vip},
                    {"address": other["spare_ip"], "services": ["data"], "type": "vip",
                     "attached_servers": [{"name": realm["server"]}]})
        if r.status_code == 200:
            leftovers.append(f"network interface {vip}")
        check(not_permitted(r),
              f"{name} token is not permitted to create a VIP at {other['spare_ip']} "
              f"({other_name}-subnet) attached to {realm['server']} "
              f"(HTTP {r.status_code}: {error_text(r)})")

        r = fb.call("POST", "/resource-accesses/batch", body=[{
            "resource": {"name": f"{other_name}-subnet", "resource_type": "subnets"},
            "scope": {"name": name, "resource_type": "realms"},
        }])
        # "already accessible" would mean realm A already has B's subnet.
        already = "already accessible" in r.text or "already exists" in r.text
        if r.status_code == 200:
            leftovers.append(f"resource access: {other_name}-subnet -> realm {name}")
        check(not_permitted(r),
              f"{name} token is not permitted to give realm {name} access to {other_name}-subnet "
              f"(HTTP {r.status_code}: {error_text(r)})"
              + (" -- the realm ALREADY HAS access to that subnet" if already else ""))

    # ------------------------------------------------------------------
    # This runs after Check 4 because it uses the spare IPs, and Check 4
    # needs them to be free.
    heading("Control: can each realm's token create a VIP on its own subnet?")
    for realm, other in pairs:
        fb, name = realm["fb"], realm["name"]
        vip = f"{name}::{PROBE_VIP_OWN}"
        r = fb.call("POST", "/network-interfaces", {"names": vip},
                    {"address": realm["spare_ip"], "services": ["data"], "type": "vip",
                     "attached_servers": [{"name": realm["server"]}]})
        if r.status_code == 200:
            leftovers.append(f"network interface {vip}")
            record("INFO", f"{name} token WAS allowed to create a VIP at {realm['spare_ip']} on "
                           f"{name}-subnet. So the rejection in Check 4 was because the subnet "
                           f"belongs to {other['name']}, not because the token cannot create VIPs.")
        else:
            record("INFO", f"{name} token was NOT allowed to create a VIP even on its own "
                           f"subnet ({error_text(r)}). The realm's token cannot create network "
                           f"interfaces anywhere, so it cannot attach its realm to any subnet, "
                           f"{other['name']}'s included.")


def cleanup(realms):
    """Delete each realm's test export, file system and export policy with
    the realm's own token. A file system has to have NFS turned off before
    it can be destroyed, and has to be destroyed before it can be
    eradicated (deleted for good). The policy can only be deleted once no
    export uses it."""
    heading("Cleanup: delete the test exports, file systems and export policies")
    for realm in realms:
        fb, name = realm["fb"], realm["name"]
        fs = f"{name}::{TEST_FS}"
        steps = [
            ("delete the export", "DELETE", "/file-system-exports",
             {"names": f"{name}::{SERVER}::NFS::{export_name(name)}"}, None),
            ("turn off NFS", "PATCH", "/file-systems", {"names": fs},
             {"nfs": {"v3_enabled": False, "v4_1_enabled": False}}),
            ("destroy", "PATCH", "/file-systems", {"names": fs}, {"destroyed": True}),
            ("eradicate", "DELETE", "/file-systems", {"names": fs}, None),
            ("delete the export policy", "DELETE", "/nfs-export-policies",
             {"names": f"{name}::{TEST_POLICY}"}, None),
        ]
        for step, method, path, params, body in steps:
            r = fb.call(method, path, params, body)
            # "does not exist": setup stopped before creating it.
            if r.status_code != 200 and "does not exist" not in r.text:
                cleanup_problems.append(f"{name}: could not {step} ({error_text(r)})")
                break


def print_summary():
    heading("Summary")
    for result, description in results:
        print(f"{result:5} {description}")

    counts = {k: sum(1 for r, _ in results if r == k) for k in ("PASS", "FAIL", "INFO")}
    print(f"\n{counts['PASS']} passed, {counts['FAIL']} failed, {counts['INFO']} informational.")
    print("RESULT: realms are isolated" if counts["FAIL"] == 0
          else "RESULT: at least one isolation check FAILED")

    if cleanup_problems:
        print("\nCLEANUP DID NOT FINISH. Remove these by hand:")
        for problem in cleanup_problems:
            print(f"  - {problem}")
    else:
        print("\nCleanup: the test exports, file systems and export policies were deleted.")

    if leftovers:
        # These exist only if a realm token was allowed to create them, so
        # they are left in place for someone to look at.
        print("\nCreated by this script and NOT cleaned up (delete these by hand):")
        for item in leftovers:
            print(f"  - {item}")

    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()
