# Realm isolation test

`realm_isolation_test.py` checks that two realms on the FlashBlade are isolated
from each other. Each realm has its own NFS server, its own VIP on its own subnet (on a dedicated VLAN),
and its own API token that can manage only that realm.

The script uses each realm's own API token. It never uses an array-wide admin token.

## What it checks

| Check | What it does | Expected |
|---|---|---|
| Setup | With each realm's token, creates a file system `isolation-test-fs` in the realm with NFSv3 and NFSv4.1 enabled, and exports it on the realm's NFS server as `/isolation-test-<realm>`. The export uses a test export policy that lets **any** client mount (see below). | — |
| 1 | Runs `showmount -e` against each realm's VIP. | The VIP lists its own realm's export, and not the other realm's. |
| 2 | Through each realm's VIP, mounts that realm's export, then tries to mount the other realm's export path. Done over NFSv3 and over NFSv4.1. | The realm's own export mounts. The other realm's export can't be mounted. |
| 3 | Lists file systems with each realm's token, and looks up the other realm's test file system by name. | Each token sees only its own realm's file systems. |
| Info | Lists the subnets each realm's token can see. | Recorded only. |
| 4 | With realm A's token, tries to create a VIP on realm B's subnet attached to a realm A server. Also tries to give realm A access to realm B's subnet. Then the same from B to A. | Both attempts are refused with "Operation not permitted". A refusal for any other reason (a bad request, an address in use) counts as FAIL, because it doesn't show a permission boundary. |
| Control | With each realm's token, tries to create a second server, and a VIP on that realm's own subnet. | Recorded only. This shows whether the refusal in check 4 is specific to the other realm's subnet, or whether the token can't create network interfaces at all. |
| Cleanup | With each realm's token, deletes the test export, turns off NFS on the test file system, destroys it, eradicates it, then deletes the test export policy. | Runs even if a check fails or the script crashes partway, so the next run starts clean. |

**Why the test exports allow any client:** a realm's own export policy only lets
clients on that realm's subnet mount. That's a useful extra layer, but it's a
check on the client's IP address, so the test deliberately takes it out of the
picture. The test exports let any client mount. So in check 2, the only reason
a mount through realm A's VIP can fail is that realm A's server doesn't have the
export, not anything about the client. Mounting the realm's own export through
the same VIP and NFS version shows the mount itself works. If that mount fails,
the check for the other realm's export counts as FAIL too, because it would
prove nothing.

NFSv3 is tested because it's the only version the FlashBlade supports for NFS
over RDMA, and NFSv4.1 because most other clients use it. `showmount` (check 1)
asks the NFSv3 MOUNT service for its export list, which NFSv4 clients never
use, so check 2 mounts over both versions. The mounts use TCP; for RDMA mounts
the export check happens over TCP/UDP the same way, before any data moves over
RDMA.

Every API request and response is printed, along with the raw output of each
`showmount` and `mount` command, so the evidence for each result appears in the
output. A summary is printed at the end. The script exits with status 0 if
every check passed and 1 if any check failed.

## Prerequisites

- Two realms set up with `ansible/flashblade-realm.yaml`, plus each realm's API
  token (the `realm-admin` service account's token).
- A host that can reach the FlashBlade management address and both realms' VIPs.
  The host doesn't need to be on either realm's subnet.
- `showmount` and an NFS client on that host (`nfs-utils` on RHEL/Fedora,
  `nfs-common` on Debian/Ubuntu; built in on macOS).
- For check 2 on Linux: `sudo` rights, because mounting needs root. The script
  runs `sudo mount` / `sudo umount` and may ask for your password. On macOS it
  mounts without sudo.
- **NFSv4.1 needs a Linux host.** macOS's NFS client only supports NFSv4.0. On
  macOS, set `mount_versions = 3` in the config.
- Python 3 with `requests` (`pip install requests`).
- One unused IP address in each realm's subnet (`spare_ip` in the config).

## Running

```sh
cp config.example.ini config.ini     # then edit config.ini
export REALM_A_API_TOKEN='...'
export REALM_B_API_TOKEN='...'
python3 realm_isolation_test.py config.ini 2>&1 | tee realm-isolation-$(date +%F).log
```

`mount_versions` in the `[nfs]` section of the config sets which NFS versions
check 2 uses. It defaults to `3, 4.1`.

The script stops before changing anything if any of these is true:

- A realm's VIP or subnet can't be found.
- A `spare_ip` isn't in its realm's subnet.
- A `spare_ip` is already in use.

## Cleanup

At the end the script unmounts anything it mounted and deletes the test file
systems, exports and export policies, so it can be run again straight away. If a
cleanup step fails, the summary says `CLEANUP DID NOT FINISH` and lists what's
left. If a run was cut off before cleanup (for example, the network dropped),
the next run reuses the leftover objects and deletes them at the end.

Check 4 and the control also try to create a server and VIPs with the realm
tokens. `flashblade-realm.yaml` gives each realm's service account only the
`storage` role, scoped to its realm, and that role can't create servers or
VIPs. So nothing is created and there's nothing more to clean up. If a realm's
account were ever given a broader role, these attempts could succeed. The
script would then leave the objects in place and list them at the end of the
summary. Delete those by hand before the next run, because preflight stops if
a spare IP is still in use.

## Results

### 2026-11-23: moc-pure-fb-01, Purity//FB 4.8.5

**Result: 22 passed, 0 failed, 6 informational. The realms are isolated.**

Check 2 covered both NFSv3 and NFSv4.1.

| | Realm A | Realm B |
|---|---|---|
| Realm | `isolation-a` | `isolation-b` |
| Subnet / VLAN | `isolation-a-subnet` 10.8.0.0/24, VLAN 2305 | `isolation-b-subnet` 10.8.1.0/24, VLAN 2306 |
| NFS server VIP | 10.8.0.10 | 10.8.1.10 |
| Spare IP used in check 4 | 10.8.0.20 | 10.8.1.20 |

Both realms were created with the `flashblade_realm` role from
`ansible/flashblade-realm.yaml`, with these two realms as the only entries in
`realms`. The one change was that the realm tokens were saved to local files
instead of being uploaded to AWS Secrets Manager. The test ran from an Ubuntu
24.04 (arm64) VM outside both realm subnets, routed to both VIPs.

**Check 1: `showmount -e`.** Each VIP lists only its own realm's export. The `*`
is the test export policy allowing any client:

```
$ showmount -e 10.8.0.10
    Exports list on 10.8.0.10:
    /isolation-test-isolation-a         *

$ showmount -e 10.8.1.10
    Exports list on 10.8.1.10:
    /isolation-test-isolation-b         *
```

**Check 2: mounting.** Through realm A's VIP, realm A's export mounts and realm
B's doesn't, over both NFS versions. The same holds the other way round:

```
$ sudo mount -t nfs -o vers=3 10.8.0.10:/isolation-test-isolation-a /tmp/realm-isolation-k23u7y3l
    (exit status 0)

$ sudo mount -t nfs -o vers=3 10.8.0.10:/isolation-test-isolation-b /tmp/realm-isolation-0639n8bw
    mount.nfs: mounting 10.8.0.10:/isolation-test-isolation-b failed, reason given by server: No such file or directory
    (exit status 32)

$ sudo mount -t nfs -o vers=4.1 10.8.0.10:/isolation-test-isolation-a /tmp/realm-isolation-9ju7nchs
    (exit status 0)

$ sudo mount -t nfs -o vers=4.1 10.8.0.10:/isolation-test-isolation-b /tmp/realm-isolation-rhedlmfa
    mount.nfs: mounting 10.8.0.10:/isolation-test-isolation-b failed, reason given by server: No such file or directory
    (exit status 32)
```

**Full summary:**

```
PASS  showmount -e 10.8.0.10 (isolation-a VIP) lists isolation-a's export /isolation-test-isolation-a
PASS  showmount -e 10.8.0.10 (isolation-a VIP) does not list isolation-b's export /isolation-test-isolation-b
PASS  showmount -e 10.8.1.10 (isolation-b VIP) lists isolation-b's export /isolation-test-isolation-b
PASS  showmount -e 10.8.1.10 (isolation-b VIP) does not list isolation-a's export /isolation-test-isolation-a
PASS  NFSv3: 10.8.0.10:/isolation-test-isolation-a (isolation-a's own export) can be mounted
PASS  NFSv3: 10.8.0.10:/isolation-test-isolation-b (isolation-b's export, through isolation-a's VIP) cannot be mounted
PASS  NFSv4.1: 10.8.0.10:/isolation-test-isolation-a (isolation-a's own export) can be mounted
PASS  NFSv4.1: 10.8.0.10:/isolation-test-isolation-b (isolation-b's export, through isolation-a's VIP) cannot be mounted
PASS  NFSv3: 10.8.1.10:/isolation-test-isolation-b (isolation-b's own export) can be mounted
PASS  NFSv3: 10.8.1.10:/isolation-test-isolation-a (isolation-a's export, through isolation-b's VIP) cannot be mounted
PASS  NFSv4.1: 10.8.1.10:/isolation-test-isolation-b (isolation-b's own export) can be mounted
PASS  NFSv4.1: 10.8.1.10:/isolation-test-isolation-a (isolation-a's export, through isolation-b's VIP) cannot be mounted
PASS  isolation-a token lists its own file system isolation-a::isolation-test-fs
PASS  isolation-a token lists none of isolation-b's file systems
PASS  isolation-a token cannot look up isolation-b::isolation-test-fs by name (HTTP 400: File system does not exist. isolation-b::isolation-test-fs)
PASS  isolation-b token lists its own file system isolation-b::isolation-test-fs
PASS  isolation-b token lists none of isolation-a's file systems
PASS  isolation-b token cannot look up isolation-a::isolation-test-fs by name (HTTP 400: File system does not exist. isolation-a::isolation-test-fs)
INFO  isolation-a token can list subnets ['isolation-a-subnet']; isolation-b-subnet is not among them
INFO  isolation-b token can list subnets ['isolation-b-subnet']; isolation-a-subnet is not among them
INFO  isolation-a token was not allowed to create a server (Operation not permitted.); using isolation-a::nfs-server instead
INFO  isolation-b token was not allowed to create a server (Operation not permitted.); using isolation-b::nfs-server instead
PASS  isolation-a token is not permitted to create a VIP at 10.8.1.20 (isolation-b-subnet) attached to isolation-a::nfs-server (HTTP 400: Operation not permitted.)
PASS  isolation-a token is not permitted to give realm isolation-a access to isolation-b-subnet (HTTP 400: Operation not permitted.)
PASS  isolation-b token is not permitted to create a VIP at 10.8.0.20 (isolation-a-subnet) attached to isolation-b::nfs-server (HTTP 400: Operation not permitted.)
PASS  isolation-b token is not permitted to give realm isolation-b access to isolation-a-subnet (HTTP 400: Operation not permitted.)
INFO  isolation-a token was NOT allowed to create a VIP even on its own subnet (Operation not permitted.). The realm's token cannot create network interfaces anywhere, so it cannot attach its realm to any subnet, isolation-b's included.
INFO  isolation-b token was NOT allowed to create a VIP even on its own subnet (Operation not permitted.). The realm's token cannot create network interfaces anywhere, so it cannot attach its realm to any subnet, isolation-a's included.

22 passed, 0 failed, 6 informational.
RESULT: realms are isolated
```

**What this shows:**

- **NFS:** a realm's NFS server serves only that realm's exports. The other
  realm's export isn't listed by `showmount`, and it can't be mounted through
  the realm's VIP over NFSv3 or NFSv4.1, even though the test export policy
  lets any client in. The
  server simply doesn't have it. The client-IP restriction in the realms'
  normal export policies is an extra layer on top of this, not what the
  isolation depends on.
- **API:** a realm's token can't list or look up the other realm's file systems.
  It also sees only its own subnet.
- **Network:** a realm's token can't change networking at all. It can't create
  a server, create a VIP (on its own subnet or the other realm's), or grant its
  realm a subnet. Attaching a realm to a subnet takes an array-wide admin
  (`flashblade-realm.yaml` does it with the array admin token). So a realm
  admin can't expose their realm's NFS server on another realm's network.
- **Error codes:** the FlashBlade refuses unpermitted requests with HTTP 400 and
  `"code": 20, "message": "Operation not permitted."`, not HTTP 403.
