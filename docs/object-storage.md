## S3 Storage

The COSI driver for creating object buckets in not available yet. So far now, creating object buckets is a manual process.

## ## S3 Object Store Setup using the Pure Storage Web GUI

The flashblade object store requires the following components to be configured:

- Network Interface with "Data" Service Role
- Object Store Account
  - Object Store User under the Object Store Account
- Access Policy (assigned to user)
- Access Keys (Access Key ID + Secret Key)
- Bucket


### Network Server & Interface Setup

1. Navigate to the **Servers** tab and create a server
2. Create a **Virtual Interface** and pick the appropriate subnet
3. When creating the subnet you can assign services in this case we need to assign the 'data' service

***The subnet is the entity that gets assigned the 'data' service and then the children interfaces automatically get the data service.***

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

#### Immutable Buckets
To setup an immutable bucket, enable **Object Lock** during bucket creation and set the **Default Retention Mode** to `COMPLIANCE`. See the [Immutable Storage Setup Docs](immutable_storage_setup.md) for more detailed information

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

## OpenShift and CLI Configuration

### Create an OpenShift secret
```bash
oc create secret generic s3-access-secret \
  --from-literal=AWS_ACCESS_KEY_ID='<ACCESS_KEY>' \
  --from-literal=AWS_SECRET_ACCESS_KEY='<SECRET_KEY>' \
  --from-literal=AWS_ENDPOINT_URL=<DATA_VIP>
```

Whereby the `<DATA_VIP>` is the IP address listed on the attached interface.

### Validate access from a pod

Create a debug pod:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: s3-debug
spec:
  restartPolicy: Never
  containers:
  - name: aws-cli
    image: amazon/aws-cli:latest
    command: ["/bin/sh", "-c"]
    args:
      - sleep infinity
    envFrom:
    - secretRef:
        name: s3-access-secret
```

Then run inside the pod:

```bash
aws --endpoint-url="$AWS_ENDPOINT_URL" --no-verify-ssl s3 ls
```

A successful connection will list available buckets.

### Notes

More information is available in the [FlashBlade Object Store Documentation](https://support.everpuredata.com/r/purityfb-rest-api/flashblade-object-store-documentation-s3-api).
