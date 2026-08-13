# Portworx Installation on OpenShift

This document covers installing and validating Portworx for Everpure storage on OpenShift.

You can find the ready to deploy manifests (will need configuration changes, of course) in [`k8s`])(https://github.com/CCI-MOC/everpure-moc/tree/main/k8s) directory of this repository.

## Prerequisites

1. Create an account at https://central.portworx.com/
2. Review the Portworx system requirements:
   https://docs.portworx.com/portworx-csi/system-requirements#network-requirements

## Create `pure.json`

Create a file called `pure.json` with the details shown below. Replace the placeholder values with your environment-specific values.

```json
{
  "FlashBlades": [
    {
      "MgmtEndPoint": "management-endpoint",
      "APIToken": "token",
      "Realm": "realm",
      "NFSEndPoint": "nfs-endpoint"
    }
  ]
}
```

If you are using the global array, you can omit the `Realm` field.

The following example shows how to specify multiple FlashBlades (or FlashArrays) with topology information.

```json
{
  "FlashBlades": [
    {
      "MgmtEndPoint": "FB end point 1",
      "APIToken": "<api-token-for-fb-management-endpoint1>",
      "NFSEndPoint": "<fb-nfs-endpoint>",
      "Labels": {
        "topology.portworx.io/zone": "<zone-1>",
        "topology.portworx.io/region": "<region-1>"
      }
    },
    {
      "MgmtEndPoint": "FB end point 2",
      "APIToken": "<api-token-for-fb-management-endpoint2>",
      "NFSEndPoint": "<fb-nfs-endpoint2>",
      "Labels": {
        "topology.portworx.io/zone": "<zone-1>",
        "topology.portworx.io/region": "<region-2>"
      }
    }
  ]
}
```

## Install the Portworx Operator

Create the namespace in the OCP cluster:

```bash
oc create namespace portworx
```

Install the operator using the OCP Operators tab, selecting the `portworx` namespace.

## Generate the Portworx Spec

1. Go to https://central.portworx.com and create a new YAML spec by selecting PX-CSI and entering the OpenShift cluster details.
   - This is not strictly necessary, because you can use the provided StorageCluster resource. However, the online portal provides a convenient way to generate the StorageCluster resource.

2. Apply the generated file to the cluster.


Create a secret with the `pure.json` file:

```bash
oc create secret generic px-pure-secret --namespace portworx --from-file=pure.json=<file path>
```

This secret provides the FlashBlade details to the Portworx operator.

## Validate Installation

Verify operator pods are running:

```bash
oc get pods -n portworx -o wide | grep -e portworx -e px
```

Get the status of the Portworx cluster:

```bash
oc get stc -n portworx
```

Check for newly created storage classes:

```bash
oc get sc
```

## StorageClasses

The StorageClasses created by the operator do not include multitenancy features or references to your NFS export policy.

Here is an example StorageClass that works with a multitenant realm setup.

```yaml
allowVolumeExpansion: true
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  labels:
    operator.libopenstorage.org/managed-by: portworx
  name: pure-fb-nfsv4
mountOptions:
- nfsvers=4.1 # NFS version 4 is recommended unless NFSv3 is required for some reason like RDMA
- tcp
parameters:
  backend: pure_file
  pure_nfs_policy: 'export-policy' # you can pre-create this policy with your customizations or let the CSI driver create it.
  pure_nfs_server: "nfs-server" # must exist in the realm specified in pure.json
  pure_fb_hard_limit_enabled:  "true" # yes, its a string. Without it, the PVC can use more storage than its size.
provisioner: pxd.portworx.com
reclaimPolicy: Delete
volumeBindingMode: Immediate
```

Parameters for a StorageClass that uses TLS:

```yaml
kind: StorageClass
metadata:
  labels:
    operator.libopenstorage.org/managed-by: portworx
  name: pure-krb5p
mountOptions:
- nfsvers=4.1
- xprtsec=tls
```

To specify topology when using multiple FlashBlades (the example below does not show multitenancy):
```yaml
kind: StorageClass
apiVersion: storage.k8s.io/v1
metadata:
  name: portworx-csi-fb
provisioner: pxd.portworx.com
parameters:
  backend: "pure_file"
mountOptions:
  - nfsvers=4.1
  - tcp
allowVolumeExpansion: true
allowedTopologies:
  - matchLabelExpressions:
    - key: topology.portworx.io/zone
      values:
        - <zone-1>
    - key: topology.portworx.io/region
      values:
        - <region-1>
```


## Networking Setup

The PX-CSI controller pods must be able to reach the FlashBlade management endpoint specified in `pure.json`.

There are a few ways to make this happen:

### Route to the management endpoint from the host's default gateway

This means that every pod can reach the management endpoint. To prevent that, create an AdminNetworkPolicy.

Here's an example:

```yaml
apiVersion: policy.networking.k8s.io/v1alpha1
kind: AdminNetworkPolicy
metadata:
  name: deny-pure-storage-api
spec:
  priority: 10
  subject:
    namespaces:
      matchExpressions:
        - key: kubernetes.io/metadata.name
          operator: NotIn
          values: [portworx]
  egress:
    - name: deny-pure-api
      action: Deny
      to:
        - networks:
            - "10.3.11.50/32"
```

### Attach the network directly to the PX-CSI controller deployments

Create a NetworkAttachmentDefinition such as:

```yaml
apiVersion: "k8s.cni.cncf.io/v1"
kind: NetworkAttachmentDefinition
metadata:
  name: eno2-storage-net
spec:
  config: '{
      "cniVersion": "0.3.1",
      "type": "macvlan",
      "master": "eno2",
      "mode": "bridge",
      "ipam": {
        "type": "whereabouts",
        "range": "10.8.0.0/24", # in our case, the route to the management endpoint is on the storage network
        "range_start": "10.8.0.13",
        "range_end": "10.8.0.19",
        "gateway": "10.8.0.1",
        "routes": [
          {
            "dst": "10.3.11.50/32",
            "gw": "10.8.0.1"
          }
        ]
      }
    }'
```

Scale the Portworx Operator deployment to 0; otherwise, it will remove the annotation that attaches the network to the deployment.
There will be a supported way to do this in future releases of the Portworx Operator.

```bash
oc -n openshift-operators scale  deployment portworx-operator --replicas=0
```

Patch the CSI controller Deployment:

```json
oc patch deployment px-pure-csi-controller -n portworx --patch '{
  "spec": {
    "template": {
      "metadata": {
        "annotations": {
          "k8s.v1.cni.cncf.io/networks": "eno2-storage-net"
        }
      }
    }
  }
}'
```

### Set the management and data interfaces in the StorageCluster resource

This needs to happen before you create the StorageCluster. It has also not been tested yet, so it is unclear whether it will work; I wanted to document it for reference.

```
➜  ~ oc explain storagecluster.spec.network
GROUP:      core.libopenstorage.org
KIND:       StorageCluster
VERSION:    v1

FIELD: network <Object>

DESCRIPTION:
    Network is to specify network configuration for the selected nodes, similar
    to the one [specified at cluster level](#network-configuration). If this
    network configuration is empty, then cluster level values are used.

FIELDS:
  dataInterface	<string>
    DataInterface is the network interface used by driver for data traffic

  mgmtInterface	<string>
    MgmtInterface is the network interface used by Portworx for control plane
    traffic
```

## Creating a PVC

Create a PVC referencing the StorageClass and mount it on a pod.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: foo
  namespace: portworx
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: pure-fb-nfsv4
  resources:
    requests:
      storage: 1Gi
```
