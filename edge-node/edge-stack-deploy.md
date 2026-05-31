# Edge stack deployment

Step-by-step setup for a **fresh edge VM**: MicroK8s, local Docker registry, build/push `ms-tod-app`, and deploy the edge stack from this directory.

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

Microservice deployments use image **`localhost:5000/ms-tod-app:v1`**.

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

## 5. Build and push `ms-tod-app`

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

## 6. Pre-deploy edits

### A. App code hostPath

Edit `ms-speed/pv-tod-code.yaml` — set `hostPath.path` to where ToD app code lives on the edge host:

```yaml
hostPath:
  path: "/home/hassaan/tod/tod-code"   # adjust user/path
```

Create the directory and place (or symlink) the `tod-code` tree:

```bash
mkdir -p ~/tod/tod-code
```

### B. MQTT bridge addresses

Edit `broker/mosquitto-conf.yaml` if OBU/RDS LAN IPs differ from:

- OBU: `192.168.205.13:31883`
- RDS: `192.168.205.77:31883`

Bridge topic routing (edge hub):

| Bridge | Out (edge → remote) | In (remote → edge) |
|--------|---------------------|---------------------|
| **obu** | `set/#` | `get/#` |
| **rds** | `get/#` | `set/#` |

See repo [README.md](../README.md) for MQTT topology and known bridge issues.

---

## 7. Deploy edge stack

Run from **`edge-node/`**:

```bash
cd ~/repos/tod/edge-node

microk8s kubectl create namespace tod

# Storage
microk8s kubectl apply -f storageclass/storageclass-local.yaml
microk8s kubectl apply -f ms-speed/pv-tod-code.yaml
microk8s kubectl apply -f ms-speed/pvc-ms-speed.yaml

# MQTT broker
microk8s kubectl apply -f broker/mosquitto-conf.yaml
microk8s kubectl apply -f broker/deployment-broker-mem-limit.yaml
microk8s kubectl apply -f broker/service-broker.yaml

# Broker IP for microservices (update in step 8)
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

All pods should reach **Running**.

---

## 8. Configure microservice broker IP

Microservices read broker address from ConfigMap `ms-ip`:

```bash
microk8s kubectl get svc broker -n tod
# note CLUSTER-IP (e.g. 10.152.183.x)

microk8s kubectl edit configmap ms-ip -n tod
# BROKERIP: <broker ClusterIP>
# BROKERPORT: "1883"

microk8s kubectl rollout restart deployment -n tod ms-direction ms-cruise ms-speed
```

---

## 9. Verify broker and bridges

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

## 10. Bridge flapping (known issue)

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
| Image | `ms-tod-app:v1` listed in registry tags |
| Stack | All pods **Running** in namespace `tod` |
| ConfigMap | `ms-ip` **BROKERIP** = broker ClusterIP |

---

## Optional: reduce CPU on edge

After building and pushing the image, you can stop Docker if you do not rebuild often on edge:

```bash
sudo snap stop docker
```

MicroK8s uses its own containerd; the registry container stops with Docker. Start Docker again when you need to build/push: `sudo snap start docker`.

---

## File reference

| Path | Purpose |
|------|---------|
| `storageclass/storageclass-local.yaml` | Local storage class |
| `ms-speed/pv-tod-code.yaml` | PV for app code (hostPath) |
| `ms-speed/pvc-ms-speed.yaml` | PVC bound to PV |
| `broker/mosquitto-conf.yaml` | Central edge broker + OBU/RDS bridges |
| `broker/deployment-broker-mem-limit.yaml` | Mosquitto deployment |
| `broker/service-broker.yaml` | NodePort 31883 |
| `ms-speed/cm-ms-IPs.yaml` | Broker IP/port for microservices |
| `ms-direction/`, `ms-cruise/`, `ms-speed/` | Microservice deployments |


## VM Networking
The following should be content of `/etc/netplan/50-cloud-init.yaml`
```network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: true
      dhcp4-overrides:
        use-routes: false
    enp0s8:
      dhcp4: false
      addresses:
        - 192.168.205.76/24
      routes:
        - to: default
          via: 192.168.205.1
```
Then do `sudo netplan apply`
