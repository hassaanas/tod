# tod

Tele-operated Driving (ToD) use case implementation. Microservices are developed in Python and deployed on Kubernetes (k8s) clusters. Four single-node k8s clusters are used: **edge**, **cloud**, **RDS**, and **OBU** (see directories `edge-node/`, `cloud-node/`, `rds-node/`, `obu-node/`).

## Reference

H. Siddiqui and F. Khendek, *Microservices for Reliable Safety-Critical Cellular IoT Systems — A Case Study*, in GLOBECOM 2024 - 2024 IEEE Global Communications Conference, Dec. 2024, pp. 1455–1460. doi: [10.1109/GLOBECOM52923.2024.10901455](https://doi.org/10.1109/GLOBECOM52923.2024.10901455)

This paper explains the use case, architecture, and implementation. Please cite it if you reuse this code.

---

## Prerequisites (edge node example)

- [MicroK8s](https://microk8s.io/) (single-node cluster)
- Docker (snap or package) for building images and running a local registry
- User in the `microk8s` group: `sudo usermod -a -G microk8s $USER` (re-login afterward)

Useful addons:

```bash
sudo microk8s enable dns storage
# optional: sudo microk8s enable helm3
```

Verify the cluster:

```bash
microk8s kubectl get nodes   # node should be Ready
```

---

## Local Docker registry (`localhost:5000`)

Microservice deployments pull **`localhost:5000/ms-tod-app:v1`**. Run a local registry on the same machine that builds and runs MicroK8s (typically the edge host):

```bash
docker run -d -p 5000:5000 --restart=always --name registry registry:2
```

Allow insecure pushes/pulls for Docker CLI (if push fails with TLS errors), in `/etc/docker/daemon.json`:

```json
{
  "insecure-registries": ["localhost:5000", "127.0.0.1:5000"]
}
```

Restart Docker (`sudo snap restart docker` or `sudo systemctl restart docker`).

Check the registry:

```bash
curl -s http://localhost:5000/v2/_catalog
curl -s http://localhost:5000/v2/ms-tod-app/tags/list
```

### MicroK8s containerd — use `config_path`, not `mirrors`

MicroK8s configures containerd with **`registry.config_path`**. Do **not** add legacy `[plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:5000"]` blocks to `containerd.toml` or `containerd-template.toml`. Newer containerd rejects having both `config_path` and `mirrors`, which prevents the CRI plugin from loading and kubelet fails with:

`unknown service runtime.v1.RuntimeService`

**Correct approach:** registry config under the certs directory:

```bash
sudo mkdir -p /var/snap/microk8s/current/args/certs.d/localhost:5000

sudo tee /var/snap/microk8s/current/args/certs.d/localhost:5000/hosts.toml <<'EOF'
server = "http://localhost:5000"

[host."http://localhost:5000"]
  capabilities = ["pull", "resolve", "push"]
EOF

sudo snap restart microk8s.daemon-containerd
```

If you previously added mirror lines to `containerd-template.toml`, remove them from both `containerd-template.toml` and `containerd.toml`, then restart containerd.

---

## Build and push `ms-tod-app` image

The runtime image is defined in `docker-images/Dockerfile-tod-app-v2` (Python 3.11, `paho-mqtt`, `stress-ng`). Application code is mounted via a PVC at runtime, not baked into the image.

From the repository root:

```bash
cd /path/to/tod

docker build \
  -f docker-images/Dockerfile-tod-app-v2 \
  -t localhost:5000/ms-tod-app:v1 \
  .

docker push localhost:5000/ms-tod-app:v1
```

To use a new tag, update `image:` in the deployment YAML under each node directory (e.g. `edge-node/ms-speed/deployment-ms-speed-obu.yaml`).

---

## Edge stack deployment

All edge resources use namespace **`tod`**. Apply in order so storage and the broker exist before microservices.

```bash
microk8s kubectl create namespace tod

cd edge-node

# Storage (adjust hostPath in ms-speed/pv-tod-code.yaml for your app code path)
microk8s kubectl apply -f storageclass/storageclass-local.yaml
microk8s kubectl apply -f ms-speed/pv-tod-code.yaml
microk8s kubectl apply -f ms-speed/pvc-ms-speed.yaml

# MQTT broker
microk8s kubectl apply -f broker/mosquitto-conf.yaml
microk8s kubectl apply -f broker/deployment-broker-mem-limit.yaml
microk8s kubectl apply -f broker/service-broker.yaml

# Shared broker IP/port for microservices (update IP after broker Service is created)
microk8s kubectl apply -f ms-speed/cm-ms-IPs.yaml

# Microservices
microk8s kubectl apply -f ms-direction/deployment-ms-direction.yaml
microk8s kubectl apply -f ms-cruise/deployment-ms-cruise.yaml
microk8s kubectl apply -f ms-speed/deployment-ms-speed-obu.yaml
```

Check status:

```bash
microk8s kubectl get pods,svc -n tod
```

### Broker IP ConfigMap

`edge-node/ms-speed/cm-ms-IPs.yaml` sets `BROKERIP` and `BROKERPORT` for microservices. After the broker Service is running, set `BROKERIP` to the broker ClusterIP (or appropriate reachable address):

```bash
microk8s kubectl get svc broker -n tod
# edit cm-ms-IPs.yaml or:
microk8s kubectl edit configmap ms-ip -n tod
```

Then restart deployments that consume the ConfigMap.

### Persistent volume host path

`ms-speed/pv-tod-code.yaml` uses a `hostPath` (default in repo: `/home/ubuntu/tod/tod-code`). Change this to the directory on the edge node where ToD application code lives.

### Broker image

The broker deployment uses `eclipse-mosquitto:latest` from Docker Hub. A custom image at `localhost:5000/mqtt-broker:latest` is commented in the deployment manifest if you build and push your own broker image.

---

## Other node roles

The same patterns apply to **cloud**, **RDS**, and **OBU** nodes using manifests under `cloud-node/`, `rds-node/`, and `obu-node/`. Each is intended as a single-node MicroK8s (or k8s) cluster with its own broker and microservices.

---

## MicroK8s troubleshooting (quick reference)

| Symptom | Likely cause |
|--------|----------------|
| `connection refused` on `127.0.0.1:16443` | API server / cluster not started; run `sudo microk8s start` |
| `microk8s is not running` but API port listens | Kubelet crash — check `sudo snap logs microk8s.daemon-kubelite` |
| `unknown service runtime.v1.RuntimeService` | containerd CRI plugin not loaded — often `mirrors` + `config_path` conflict (see above) |
| `failed to load plugin io.containerd.grpc.v1.cri` … `mirrors` cannot be set when `config_path` is provided | Remove mirror stanzas; use `certs.d/localhost:5000/hosts.toml` |
| `microk8s status` Python traceback on `all,ingress` | Cluster may still work; use `microk8s kubectl get nodes`. Enable ingress addon if needed: `sudo microk8s enable ingress` |
| `localnode.yaml` missing in `microk8s inspect` | Harmless inspect-script warning on newer dqlite; ignore |

Recovery on a dev node (destroys cluster state):

```bash
sudo microk8s stop
sudo microk8s reset --destroy-storage
sudo microk8s start
sudo microk8s status --wait-ready
```

---

## Future improvements

### Kustomize (recommended next step)

For repeatable, per-site deploys without Helm, add a [Kustomize](https://kustomize.io/) layout:

- **base/** — current YAML under `edge-node/` (and other nodes)
- **overlays/** — per-environment patches (broker IP, image tags, `hostPath`, registry)

Deploy with:

```bash
kubectl apply -k edge-node/overlays/<site-name>
```

This avoids editing manifests by hand for each edge node while keeping plain YAML in Git.

### Helm (optional, later)

A Helm chart is useful if you deploy many edge nodes or want `helm upgrade` / `helm rollback` in CI/CD. For a single edge host, Kustomize or a small shell script is usually enough.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `edge-node/` | Edge broker, microservices, storage |
| `cloud-node/` | Cloud-side stack |
| `rds-node/` | RDS stack |
| `obu-node/` | OBU stack |
| `docker-images/` | `Dockerfile-tod-app`, `Dockerfile-tod-app-v2` |
| `prometheus/` | Monitoring manifests |
| `storageclass/` | Shared storage class example |
