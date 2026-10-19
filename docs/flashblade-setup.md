# Pure FlashBlade Setup

This document describes the Pure FlashBlade configuration steps required for Everpure FlashBlade storage in MOC clusters in a secure multi-tenant fashion, as described in this document: https://support.everpuredata.com/r/nvidia/multitenancy-network-setup

Note: A max of 200 realms are supported per flashblade.

## Quickstart

At a high level, we want to create a realm with a dedicated server that has an interface on a dedicated, isolated VLAN.

## Create a Realm for Your Cluster

From the Pure dashboard, click Storage and navigate to the Realms tab. Create a new realm. Avoid reusing realms for production clusters, because the credentials are scoped to a realm.

## Creating a Management Access Policy and a User

Under Policies > Management Access, create a policy scoped to your realm and assign it the "storage" role.

Next, go to Settings > Users. Create a serviceaccount with the access policy set to the one created in the previous step.
Then generate token for this service account. We will use this token with the CSI driver.

## Create a Server

Within the same realm, create a server. This server is used to provide NFS and object storage from that realm. When you create the server, it will prompt you to create an interface; this is where you select the subnet on the dedicated VLAN for the cluster and assign an IP. The name of the server and the NFS endpoint will be used by the CSI driver.

When creating the server it'll prompt you to Choose a DNS configuration. Choose "Create new DNS configuration". Ask your network admin what settings to choose here. For our flashblade installation set:

DNS Configuration Scope: <your realm>
Domain: massopen.cloud
Nameservers: The gateway of the network since we server DNS on it.
Source: Resuse new. It will use the newly created interface.

## Create a Filesystem in Your Realm

Because we will be using the CSI driver, we do not need to manually create any filesystems. For testing, however, we can create one.

## Create an NFS Export Policy

If an NFS export policy does not exist, the CSI driver will create one automatically, but it may not specify all the features we need.

With an NFS export policy, we can specify transport security options such as TLS or Kerberos privacy (krb5p). We can also restrict which clients can mount NFS volumes by specifying a network CIDR.

We should stick to root-squash unless there is a specific need.

There is a bug in the CSI driver where a user-created NFS export policy is deleted by the CSI driver. To work around it, create a small dummy filesystem manually and export it using your NFS export policy. https://github.com/CCI-MOC/ops-issues/issues/1752

## Create a Filesystem Export

From the menu in our realm, we can create a filesystem export by choosing the filesystem and selecting the policy to use for the export. For dynamically provisioned volumes created by the CSI driver, there is nothing to do.

## TLS Configuration

To have FlashBlade serve an SSL certificate on an interface that is part of a realm, follow these steps.

1. Go to Settings > Certificates > Array Certificates.
   - From here, either generate a self-signed certificate or import one.
   - The certificate's Subject Alternative Names should include the IP address of your NFS interface.
   - FlashBlade does not show a realm to choose when creating this certificate. To scope it to a realm, name the certificate as `realm-name::certificate-name`. The `::` does the trick.

2. Go to Policies > Network Security > TLS > TLS Policies.
   - Create a new TLS policy. This menu will show the option to scope it to your realm. Then choose the certificate created in step 1.

3. After you create the policy, click on it. On the right, you will see the Members section. Add the interface of your server here. This associates the certificate with the interface.

The `flashblade_realm` Ansible role does all three steps. It always includes the realm's `interface_address` in the certificate's Subject Alternative Names, since clients reach the realm by that IP. If the realm is also reached by other names, list them in `cert_subject_alternative_names` on the realm:

```yaml
realms:
  - name: jetty
    interface_address: 10.9.6.10
    cert_subject_alternative_names:
      - jetty-nfs.massopen.cloud
```

Re-running the role regenerates the certificate with a new key, so clients that trust the old certificate need the new one imported.

### TLS-only realms

The role creates two NFS export policies in each realm: `export-policy`, which allows cleartext, and `export-policy-tls`, which requires TLS. For a realm that must never serve cleartext NFS, for example a cluster that has to meet NIST 800-171 or HIPAA, set `tls_only: true` on the realm:

```yaml
realms:
  - name: nist-dev-infra
    tls_only: true
```

`export-policy` then requires TLS as well. It is still created rather than left out, because the CSI driver creates any export policy a StorageClass names that does not exist, with its own defaults, so a missing `export-policy` would come back without TLS.

The role only creates policies; it does not change existing ones. For an existing realm, edit the rule of `<realm>::export-policy` and set its transport security to TLS. Do not re-run the role for this: it would also regenerate the certificate.

Clients mount with `xprtsec=tls`. On OpenShift that needs `tlshd` on every node that mounts storage.
