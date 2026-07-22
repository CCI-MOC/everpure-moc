# FlashBlade Immutable Logs Setup

This guide describes how to configure immutable log storage on a Pure Storage FlashBlade using either the S3 Object Store or a filesystem-based approach.

***Navigating the Pure Storage UI is kind of painful and often the hierarchical elements are not well organized. It can be difficult to find the correct menu item or setting.***

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [S3 Object Store Setup](#s3-object-store-setup)
  - [Create the Object Store Account](#create-the-object-store-account)
  - [Create the Bucket](#create-the-bucket)
  - [Configure Object Lock and Retention](#configure-object-lock-and-retention)
  - [Creating Users](#creating-users)
  - [Generate Access Keys](#generate-access-keys)
  - [Creating the Account Export](#creating-the-account-export)
  - [Verify S3 Immutability](#verify-s3-immutability)
- [Filesystem Setup](#filesystem-setup)
  - [Pure File SafeMode](#pure-file-safemode)
  - [WORM Policy](#worm-policy)
  - [Create the File System](#create-the-file-system)
  - [Configure Snapshot Policies](#configure-snapshot-policies)
  - [File System Export Policies/Rules](#file-system-export-policiesrules)
  - [File System Exports](#file-system-exports)
  - [Mount the File System](#mount-the-file-system)
  - [Verify Filesystem Immutability](#verify-filesystem-immutability)

## Overview

FlashBlade supports immutable log storage through two primary mechanisms:

- **S3 Object Store** — Uses S3 Object Lock with Compliance or Governance mode and a retention policy to prevent object deletion or modification.
- **Filesystem** — Uses FlashBlade snapshots and write-once policies to protect log data written over NFS.

Choose the approach that matches your application and access model.

## S3 Object Store Setup

The flashblade object store requires the following components to be configured:

- Object Store Account
  - Object Store User under the Object Store Account
- Access Policy (assigned to user)
- Access Keys (Access Key ID + Secret Key)
- Bucket
- Network Interface with "Data" Service Role

### Create the Object Store Account

Object store accounts sit one level above users and buckets in the hierarchy. So the account is the top-level logical grouping of users and buckets. Think of it like a "tenant" or "namespace boundary".

```
Object Store Account  (top-level container / tenant)
   ├── Object Store User(s)        ← one level down
   │      ├── Access Policy(ies)
   │      └── Access Key(s)
   └── Bucket(s)                    ← also one level down, sibling to Users
```

1. Log in to the FlashBlade management interface.
2. Navigate to **Storage > Object Storage > Accounts**.
3. Click **Create Account** and provide a name for the object store account.

### Create the Bucket

1. Within the new object store account, select **Buckets**.
2. Click **Create Bucket**.
3. Enter a unique bucket name and enable **Object Lock** during creation.
4. Confirm the bucket is created with Object Lock enabled.

### Configure Object Lock and Retention

1. Open the bucket settings.
2. Set the **Default Retention Mode** to `COMPLIANCE` for strict immutability, or `GOVERNANCE` if privileged deletion must remain possible.
3. Define the **Default Retention Period** based on your log retention requirements.
4. Save the retention policy.]

### Creating Users

Users sit one level below the object store account and are attached to access policies and access keys. These policies **only** define the user's access rights and what actions they are allowed to perform, while access keys are used for authentication.

1. Open the Object Store Account itself
2. Navigate to **Users** and click **Add User**.
3. Enter a unique username for the user.
4. Add the relevant access policies to the user.
5. A user prompt will appear requesting if you want to generate an access key for the user.

### Generate Access Keys

1. Go to **Object Storage >  Accounts (whatever the account name is) > Users (whatever the user name is) > Access Keys > Create**.
2. Create a new access key for the object store account.
3. Record the **Access Key ID** and **Secret Access Key** securely.

### Creating the Account Export

An Object Store Account Export is the object that binds an Object Store Account to a specific network Server, exposing that account's S3 endpoint over a particular server/network path.

1. Go to **Object Storage >  Accounts (whatever the account name is) > Account Export >> Create**.
2. Select the scope, account, server, and policy along with the enabled check mark.

### Verify S3 Immutability

1. Write a test object to the bucket.
2. Attempt to delete or overwrite the object before the retention period expires.
3. Confirm the operation is rejected by the FlashBlade S3 endpoint.

## Filesystem Setup

### Pure File SafeMode

According to page 65 of the [FlashBlade Admin Guide](https://support.everpuredata.com/v/u/pd/flashblade_admin_guide_4.6.7.pdf) 
>"Pure File SafeMode is configured during installation and is designed to protect the system from accidental changes"

So it seems like something that should be enabled during installation. With Purity 6.4.10 and onward, Auto-on SafeMode is turned on by default. [Everpure Article](https://blog.everpuredata.com/products/how-to-protect-your-data-from-ransomware-with-safemode-snapshots/)

### WORM Policy

WORM Policies sit under realms or arrays but are applied to file systems.

1. In the default menu open WORM Policies.
2. Create a WORM policy with the desired options:
    - Min Retention - Ensures logs cannot be deleted before the minimum required retention period
    - Max Retention - Prevents logs from being kept longer than policy allows (data governance)
    - Default Retention - Auto-locks logs written by systems that don't explicitly set a retention time (most log shippers don't)
    - Mode: **Compliance** - Makes the policy itself immutable so nobody can reduce retention periods after the fact
    - Retention Lock: **Locked** - Prevents even storage admins from deleting logs early so no override possible
3. When creating the file system, apply the WORM policy. There should be a checkbox to enable WORM mode.

**Don't worry if this checkbox is not available immediately. sometimes the UI takes a while to update but should give you that option once you've created a WORM policy**

***Once a file system is set to WORM mode, it cannot be reversed. This is permanent!***


### Create the File System

1. Log in to the FlashBlade management interface.
2. Navigate to **Storage > File Systems**.
3. Click **Create File System** and provide a name and size.
4. Configure NFS export settings with appropriate client access rules.

***Our current architecture for the MOC should we use a file system, will likely be NFS4.1 because it supports auth like TLS or kerberos. NFSv3 will be used if using RDMA. SMB is not used at all. TLS will be used. Mutual TLS is a maybe.******

### Configure Snapshot Policies

1. In the default menu open Snapshots Policies.
2. Create or assign a snapshot policy that matches the usual log retention schedule.
3. In the snapshot menu, attach Members (File Systems), to the snapshot policy to bind the snapshot policy to the file system.


### File System Export Policies/Rules

These sections are combined because creating a File System Policy prompts you to create a Rule also.

1. Navigate to the NFS Export Rules section
2. Create an NFS policy which would then prompt you to create an NFS Export Rule and select the appropriate security protocol for our compliance requirements

***07/21/2026 - As the current situation stands, we have no kerberos environment to authenticate NFS users nor has that been planned. So any `krb` security protocol cannot be used***

***If we want authentication via `krb`, we will need to set up some sort of kerberos environment***

### File System Exports
File system exports are used to bind a file system to an export name with a specified file system policy 
1. Navigate to the File systems menu and create a File System Export
2. Choose the realm (array), server, file system, name and export policy.

***The export name is what would be used to connect to the file system***
### Mount the File System

On the client host, mount the FlashBlade NFS export:

```bash
sudo mount -t nfs <flashblade-fqdn>:/<export-name>
```

### Verify Filesystem Immutability

***Binding a WORM policy to a FlashBlade file system does not automatically make every file immutable. It makes the file system WORM-capable and supplies the retention rules. Each individual file must then be committed into the WORM state via the `chmod -w` command or `chmod a-w` command .*** 

[Official Documentation](https://support.everpuredata.com/api/khub/documents/v01YXt1zRNBXs2AjEHVQiw/content) **See page 66 under section** *Committing WORM Files*

1. Write a test log file to the mounted path and apply the `chmod -w` command or `chmod a-w` command to commit it into the WORM state.
2. Confirm that a snapshot after the specified interval exists and protects the data.
3. Attempt to delete or modify the file and it should be denied.
