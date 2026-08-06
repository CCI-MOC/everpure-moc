# FlashBlade Immutable Logs Setup

This guide describes how to configure immutable log storage on a Pure Storage FlashBlade using either the S3 Object Store or a filesystem-based approach.

## Table of Contents

- [Overview](#overview)
- [S3 Object Store Immutable Bucket Setup](#s3-object-store-immutable-bucket-setup)
  - [Creating an Immutable Bucket](#creating-an-immutable-bucket)
  - [Configure Object Lock and Retention](#configure-object-lock-and-retention)
  - [Verify S3 Immutability](#verify-s3-immutability)
- [Immutable Filesystem Setup](#immutable-filesystem-setup)
  - [Pure File SafeMode](#pure-file-safemode)
  - [WORM Policy](#worm-policy)
  - [Configure Snapshot Policies](#configure-snapshot-policies)
  - [Mount the File System](#mount-the-file-system)
  - [Verify Filesystem Immutability](#verify-filesystem-immutability)

## Overview

FlashBlade supports immutable log storage through two primary mechanisms:

- **S3 Object Store** — Uses S3 Object Lock with Compliance or Governance mode and a retention policy to prevent object deletion or modification.
- **Filesystem** — Uses FlashBlade snapshots and write-once policies to protect log data written over NFS.

Choose the approach that matches your application and access model.

## S3 Object Store Immutable Bucket Setup

Please refer to the [S3 Object Store Setup Guide](object-storage.md) for detailed instructions on setting up the S3 Object Store.

### Creating an Immutable Bucket

1. Within the new object store account, select **Buckets**.
2. Click **Create Bucket**.
3. Enter a unique bucket name and create bucket
4. After bucket creation and edit bucket settings and enable **Object Lock**
5. Confirm the bucket now has Object Lock enabled.
6. 
#### Other Settings

- Freeze Locked Objects: With Freeze Locked Objects enabled on a bucket, FlashBlade will block any attempt to delete or overwrite a locked object in that bucket.
> **IMPORTANT: If bucket versioning and Object Lock are required, Freeze Locked Objects must be disabled. Contact Pure Technical Services for assistance in setting this configuration. Note that if this configuration is set, it cannot be changed. [See page 111](https://support.everpuredata.com/v/u/pdf/flashblade_450_user_guide.pdf)**
- Eradication Mode: If set to retention-based, then all manual eradication will be prevented [See page 111](https://support.everpuredata.com/v/u/pdf/flashblade_450_user_guide.pdf)
- Retention Lock: [See page 111](https://support.everpuredata.com/v/u/pdf/flashblade_450_user_guide.pdf)
> When enabled, Retention Lock limits the ability to modify Object Lock settings and certain functions. A
Retention Lock can only be unlocked by Pure Technical Services.

**IMPORTANT: To prevent a single person being able to just delete entire buckets Object SafeMode needs to be enabled and it can be enabled with the help of Everpure technical support [See page 109](https://support.everpuredata.com/v/u/pdf/flashblade_450_user_guide.pdf)**

### Configure Object Lock and Retention

1. Open the bucket settings.
2. Set the **Default Retention Mode** to `COMPLIANCE` for strict immutability, or `GOVERNANCE` if privileged deletion must remain possible.
3. Define the **Default Retention Period** based on your log retention requirements.
4. Save the retention policy.

### Verify S3 Immutability

1. Write a test object to the bucket.
2. Attempt to delete or overwrite the object before the retention period expires.
3. Confirm the operation is rejected by the FlashBlade S3 endpoint.

## Immutable Filesystem Setup

***For basic file system setup please refer to the [Flashblade Setup Guide](flashblade-setup.md). The instructions below pertain to only file system immutability***

**Proceed with immutable storage configuration once you have a existing file system with the desired export policies, export rules and file system exports**

### Pure File SafeMode

According to page 65 of the [FlashBlade Admin Guide](https://support.everpuredata.com/v/u/pd/flashblade_admin_guide_4.6.7.pdf) 
>"Pure File SafeMode is configured during installation and is designed to protect the system from accidental changes"

So it seems like something that should be enabled during installation. With Purity 6.4.10 and onward, Auto-on SafeMode is turned on by default. [Everpure Article](https://blog.everpuredata.com/products/how-to-protect-your-data-from-ransomware-with-safemode-snapshots/)

**Without Pure File SafeMode file systems can simply be deleted by a user with sufficient privileges**

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


### Configure Snapshot Policies

1. In the default menu open Snapshots Policies.
2. Create or assign a snapshot policy that matches the usual log retention schedule.
3. In the snapshot menu, attach Members (File Systems), to the snapshot policy to bind the snapshot policy to the file system.

### Mount the File System

On the client host, mount the FlashBlade NFS export. For example:

```bash
sudo mkdir -p /mnt/logs
sudo mount -t nfs <flashblade-fqdn>:/<export-name> /mnt/logs
```

### Verify Filesystem Immutability

***Binding a WORM policy to a FlashBlade file system does not automatically make every file immutable. It makes the file system WORM-capable and supplies the retention rules. Each individual file must then be committed into the WORM state via the `chmod -w` command or `chmod a-w` command .*** 

[Official Documentation](https://support.everpuredata.com/api/khub/documents/v01YXt1zRNBXs2AjEHVQiw/content) **See page 66 under section** *Committing WORM Files*

1. Write a test log file to the mounted path and apply the `chmod -w` command or `chmod a-w` command to commit it into the WORM state. 

There are default retention times as defined in the WORM policy. To check file retention time run:

```
stat <file-name>
```

Without specifying a retention time, the retention time should match the *Default Retention* field in the WORM policy

2. Confirm that a snapshot after the specified interval exists and protects the data.
3. Attempt to delete or modify the file and it should be denied.
