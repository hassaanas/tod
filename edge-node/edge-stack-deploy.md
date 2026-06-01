# Edge stack deployment

Step-by-step setup for a **fresh edge VM**: MicroK8s, local Docker registry, broker image, and deploy the edge stack from this directory.

The **primary role of the edge node is the central MQTT broker** (bridges to OBU and RDS). Microservices on edge are optional.

## Assumptions

- Ubuntu 24.04, hostname **`edge`**
- Example LAN IP **`192.168.205.12`** (adjust if your network differs)
- OBU and RDS brokers already running with NodePort **31883**
- Repo cloned at `~/repos/tod`

| Remote | Example address |
|--------|-----------------|
| OBU broker | `192.168.205.13:31883` |
| RDS broker | `192.168.205.77:31883` |

---

## 1. Base packages

```bash
sudo apt update
sudo apt install -y git curl

sudo snap install microk8s --classic
sudo snap install docker

sudo usermod -a -G microk8s,docker $USER
newgrp microk8s   # or log out and back in
```

---

## 2. MicroK8s

```bash
sudo microk8s status --wait-ready
sudo microk8s enable dns storage

microk8s kubectl get nodes   # edge should be Ready
```

**Important:** Do **not** add `[plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:5000"]` to `containerd-template.toml` or `containerd.toml`. Newer containerd rejects `mirrors` when `config_path` is set and kubelet fails with `unknown service runtime.v1.RuntimeService`. Use `certs.d` only (step 4).

---

## 3. Local Docker registry (`localhost:5000`)

```bash
docker run -d -p 5000:5000 --restart=always --name registry registry:2

sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "insecure-registries": ["localhost:5000", "127.0.0.1:5000"]
}
EOF
sudo snap restart docker

curl -s http://localhost:5000/v2/_catalog
```

---

## 4. MicroK8s: pull from local registry

Configure containerd via **`config_path`** (not mirrors):

```bash
sudo mkdir -p /var/snap/microk8s/current/args/certs.d/localhost:5000

sudo tee /var/snap/microk8s/current/args/certs.d/localhost:5000/hosts.toml <<'EOF'
server = "http://localhost:5000"

[host."http://localhost:5000"]
  capabilities = ["pull", "resolve", "push"]
EOF

sudo snap restart microk8s.daemon-containerd
sudo microk8s status --wait-ready
```

Verify CRI loaded:

```bash
sudo snap logs microk8s.daemon-containerd -n 15 | grep -i cri
# must NOT show: failed to load plugin io.containerd.grpc.v1.cri
```

---

## 5. Build and push broker image

Promote **Eclipse Mosquitto** to the local registry as **`localhost:5000/mqtt-broker:latest`**.

```bash
docker pull eclipse-mosquitto:latest

docker tag eclipse-mosquitto:latest localhost:5000/mqtt-broker:v1
docker push localhost:5000/mqtt-broker:v1

curl -s http://localhost:5000/v2/mqtt-broker/tags/list
```

In `broker/deployment-broker-mem-limit.yaml`, use the local image (uncomment registry line, comment Hub line if present):

```yaml
- image: localhost:5000/mqtt-broker:v1
# - image: eclipse-mosquitto:latest
```

Alternatively, skip the registry and pull **`eclipse-mosquitto:latest`** from Docker Hub directly in the deployment (no push step).

---

## 6. Build and push `ms-tod-app` (optional)

Only needed if you deploy **microservices** on edge (`ms-direction`, `ms-cruise`, `ms-speed`). Skip this section for **broker-only** edge.

From the repository root:

```bash
cd ~/repos/tod

docker build \
  -f docker-images/Dockerfile-tod-app-v2 \
  -t localhost:5000/ms-tod-app:v1 \
  .

docker push localhost:5000/ms-tod-app:v1

curl -s http://localhost:5000/v2/ms-tod-app/tags/list
```

Application code is mounted at runtime via PVC; it is not baked into the image.

---

## 7. Pre-deploy edits

### A. MQTT bridge addresses

Edit `broker/mosquitto-conf.yaml` if OBU/RDS LAN IPs differ from:

- OBU: `192.168.205.13:31883`
- RDS: `192.168.205.77:31883`

Bridge topic routing (edge hub):

| Bridge | Out (edge → remote) | In (remote → edge) |
|--------|---------------------|---------------------|
| **obu** | `set/#` | `get/#` |
| **rds** | `get/#` | `set/#` |

See repo [README.md](../README.md) for MQTT topology and known bridge issues.

### B. App code hostPath (optional — microservices only)

If deploying microservices, edit `ms-speed/pv-tod-code.yaml`:

```yaml
hostPath:
  path: "/home/hassaan/tod/tod-code"   # adjust user/path
```

```bash
mkdir -p ~/tod/tod-code
```

---

## 8. Deploy edge stack

Run from **`edge-node/`**:

```bash
cd ~/repos/tod/edge-node

microk8s kubectl create namespace tod

# MQTT broker (required)
microk8s kubectl apply -f broker/mosquitto-conf.yaml
microk8s kubectl apply -f broker/deployment-broker-mem-limit.yaml
microk8s kubectl apply -f broker/service-broker.yaml
```

**Broker only** — stop here and verify (step 10).

**Full stack (optional microservices)** — also apply:

```bash
microk8s kubectl apply -f storageclass/storageclass-local.yaml
microk8s kubectl apply -f ms-speed/pv-tod-code.yaml
microk8s kubectl apply -f ms-speed/pvc-ms-speed.yaml

microk8s kubectl apply -f ms-speed/cm-ms-IPs.yaml

microk8s kubectl apply -f ms-direction/deployment-ms-direction.yaml
microk8s kubectl apply -f ms-cruise/deployment-ms-cruise.yaml
microk8s kubectl apply -f ms-speed/deployment-ms-speed-obu.yaml
```

Check status:

```bash
microk8s kubectl get pods,svc -n tod
```

Broker pod should be **Running**; microservice pods **Running** only if you applied step 6 and the optional manifests above.

---

## 9. Configure microservice broker IP (optional)

Only if microservices are deployed. They read broker address from ConfigMap `ms-ip`:

```bash
microk8s kubectl get svc broker -n tod
# note CLUSTER-IP (e.g. 10.152.183.x)

microk8s kubectl edit configmap ms-ip -n tod
# BROKERIP: <broker ClusterIP>
# BROKERPORT: "1883"

microk8s kubectl rollout restart deployment -n tod ms-direction ms-cruise ms-speed
```

---

## 10. Verify broker and bridges

```bash
microk8s kubectl logs -n tod deploy/broker --tail=30

# Remote NodePorts must be reachable from edge
nc -zv 192.168.205.13 31883
nc -zv 192.168.205.77 31883
```

Optional shell aliases (`~/.bashrc`):

```bash
alias k='microk8s kubectl'
alias kg='microk8s kubectl get'
```

---

## 11. Bridge flapping (known issue)

If OBU/RDS logs show `exceeded timeout` every ~60–90s for `edge_to_obu` / `edge_to_rds`, MQTT keepalive is likely lost over **NodePort (`:31883`)**.

The edge ConfigMap already includes:

```conf
keepalive_interval 30
restart_timeout 30
start_type automatic
```

If flapping continues:

1. Enable **`hostNetwork: true`** on broker Deployments on OBU, RDS, and edge
2. Change bridge addresses in `broker/mosquitto-conf.yaml` to **`:1883`** on node LAN IPs

Full details: [README.md — Known issue: edge broker bridge flapping](../README.md#known-issue-edge-broker-bridge-flapping).

---

## Checklist

| Step | Done when |
|------|-----------|
| MicroK8s | `kubectl get nodes` → edge **Ready** |
| Registry | `curl localhost:5000/v2/_catalog` succeeds |
| containerd | No CRI plugin errors in snap logs |
| Broker image | `mqtt-broker:latest` in registry (or Hub image in deployment) |
| Broker pod | **Running** in namespace `tod` |
| ms-tod-app (optional) | `ms-tod-app:v1` in registry, if using edge microservices |
| ConfigMap (optional) | `ms-ip` **BROKERIP** = broker ClusterIP |

---

## Optional: reduce CPU on edge

After building and pushing images, you can stop Docker if you do not rebuild often on edge:

```bash
sudo snap stop docker
```

MicroK8s uses its own containerd; the registry container stops with Docker. Start Docker again when you need to build/push: `sudo snap start docker`.

---

## File reference

| Path | Purpose |
|------|---------|
| `broker/mosquitto-conf.yaml` | Central edge broker + OBU/RDS bridges |
| `broker/deployment-broker-mem-limit.yaml` | Mosquitto deployment |
| `broker/service-broker.yaml` | NodePort 31883 |
| `storageclass/storageclass-local.yaml` | Local storage class (microservices) |
| `ms-speed/pv-tod-code.yaml` | PV for app code (microservices) |
| `ms-speed/pvc-ms-speed.yaml` | PVC bound to PV (microservices) |
| `ms-speed/cm-ms-IPs.yaml` | Broker IP/port for microservices |
| `ms-direction/`, `ms-cruise/`, `ms-speed/` | Microservice deployments (optional) |
