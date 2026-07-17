## S3 Storage

The COSI driver for creating object buckets in not available yet. So far now, creating object buckets is a manual process.

### Pure S3 setup in Pure

1. In the Pure dashboard, open `Object Store` under Storage in your realm.
2. Create a new account.
3. Create a new account export and assign the appropriate export policy.
4. Click the newly created account, create a new user, and then create a new access key.
5. Save the Access Key ID and Secret Access Key.

### Create an OpenShift secret

```bash
oc create secret generic s3-access-secret \
  --from-literal=AWS_ACCESS_KEY_ID='<ACCESS_KEY>' \
  --from-literal=AWS_SECRET_ACCESS_KEY='<SECRET_KEY>' \
  --from-literal=AWS_ENDPOINT_URL=<DATA_VIP>
```

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

More information is available in the FlashBlade Object Store Documentation:

https://support.purestorage.com/bundle/m_purityfb_rest_api/page/FlashBlade/Purity_FB/PurityFB_REST_API/S3_Object_Store_REST_API/topics/concept/c_flashblade_object_store_documentation_s3_api.html
