# OSRM EC2 Deployment Guide — FloodWatch Phase 4

Deploy the OSRM routing engine on an EC2 instance to serve flood-aware evacuation routes.

---

## Prerequisites
- AWS EC2 access (us-east-1)
- SSH key pair created
- Security group with ports 22 (SSH) and 5000 (OSRM) open

---

## Step 1: Launch EC2 Instance

| Setting | Value |
|---------|-------|
| AMI | Amazon Linux 2023 |
| Instance type | **t3.small** (2 vCPU, 2 GB) |
| Storage | 30 GB gp3 |
| Security group | Allow TCP 22, TCP 5000 |
| Key pair | Your SSH key |

---

## Step 2: Install OSRM Backend

SSH into the instance and run:

```bash
# Install Docker
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Log out and back in for group change
exit
# SSH back in

# Pull OSRM backend
docker pull osrm/osrm-backend:latest
```

---

## Step 3: Download South India OSM Data

```bash
mkdir -p /home/ec2-user/osrm-data && cd /home/ec2-user/osrm-data

# Download India-South sub-region
wget https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf
```

---

## Step 4: Process Map Data

```bash
cd /home/ec2-user/osrm-data

# Extract (takes ~5 minutes)
docker run --rm -t -v $(pwd):/data osrm/osrm-backend:latest \
  osrm-extract -p /opt/car.lua /data/southern-zone-latest.osm.pbf

# Partition
docker run --rm -t -v $(pwd):/data osrm/osrm-backend:latest \
  osrm-partition /data/southern-zone-latest.osrm

# Customize
docker run --rm -t -v $(pwd):/data osrm/osrm-backend:latest \
  osrm-customize /data/southern-zone-latest.osrm
```

---

## Step 5: Start OSRM Server

```bash
docker run -d --name osrm-server --restart always \
  -p 5000:5000 \
  -v /home/ec2-user/osrm-data:/data \
  osrm/osrm-backend:latest \
  osrm-routed --algorithm mld /data/southern-zone-latest.osrm

# Verify
curl "http://localhost:5000/route/v1/driving/80.27,13.08;80.22,13.02?overview=full&geometries=geojson"
```

---

## Step 6: Configure Lambda Environment

Set this env var on the `routingLambda` function:

```
OSRM_ENDPOINT=http://<EC2_PUBLIC_IP>:5000
OSRM_MOCK=0
```

---

## Cost Estimate

| Resource | Monthly Cost |
|----------|-------------|
| t3.small (on-demand) | ~$15/month |
| 30 GB gp3 | ~$2.40/month |
| **Total** | **~$17.40/month** |

> **Tip**: Stop the instance when not testing to save costs.
> Use `aws ec2 stop-instances --instance-ids <id>` when done.

---

## Verification

```bash
# Test route from Chennai Central to Marina Beach
curl "http://<EC2_IP>:5000/route/v1/driving/80.2707,13.0827;80.2838,13.0499?overview=full&geometries=geojson"
```

Expected: JSON response with `"code": "Ok"` and route coordinates.
