Kubernetes installation on bare metal
===


Prerequisites
---

Install and configure these components on every master node.
If you plan to use an external etcd cluster then you should consider installing that component on the dedicated, bare metal servers.

- [keepalived](./keepalived/keepalived.conf)
- [haproxy LB](./haproxy/haproxy.cfg)
- [etcd external cluster](https://coreos.com/etcd/docs/latest/v2/clustering.html) (supervisor configuration file for [etcd](./etcd/etcd.conf) included)

**Note:** Before you can start haproxy service, that will bind to floating IP, you have to allow non-local bind first
```bash
cat >> /etc/sysctl.d/99-sysctl.conf <<EOF
# Allow non-local bind
net.ipv4.ip_nonlocal_bind = 1
EOF

sysctl -p
```


Install dependencies
---

Install kubelet and all required kubernetes tools and docker engine on all hosts that participate in the kubernetes cluster,
which includes, masters and regular nodes

Add apt key and repository file
```bash
apt-get update && apt-get install -y apt-transport-https

curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -

cat > /etc/apt/sources.list.d/kubernetes.list <<EOF
deb http://apt.kubernetes.io/ kubernetes-xenial main
EOF

apt-get update
```

Install docker engine and required kubernetes packages
```bash
apt-get install -y docker-engine
apt-get install -y kubelet kubeadm kubectl kubernetes-cni
```


Primary master installation and configuration
---

Create kubeadm configuration file

**Note:** ops-kube-master.example.com => 172.16.30.30 is a floating IP

**Note:** We're using external [etcd cluster](https://coreos.com/etcd/docs/latest/v2/clustering.html) and that's why we have configured etcd endpoints inside yaml configuration, you have to remove these lines if you plan to run etcd inside kubernetes itself
```bash
cat > primary-master-config.yaml <<EOF
apiVersion: kubeadm.k8s.io/v1alpha1
kind: MasterConfiguration
etcd:
  endpoints:
  - http://172.16.28.11:2379
  - http://172.16.28.12:2379
  - http://172.16.28.13:2379
networking:
  podSubnet: 10.244.0.0/16
apiServerCertSANs:
  - ops-kube-master
  - ops-kube-master1
  - ops-kube-master2
  - ops-kube-master3
  - 172.16.30.16
  - 172.16.30.17
  - 172.16.30.18
  - 172.16.30.30
EOF
```

Provision primary master
```bash
kubeadm init --config=primary-master-config.yaml 2>&1 | tee kubeadm.log
```

#### Modify configuration files

Replace IP address for API server
```bash
for CONF in admin.conf controller-manager.conf kubelet.conf scheduler.conf; do sed -i 's/172.16.30.16:6443/172.16.30.30:8443/' /etc/kubernetes/${CONF}; done
```

Bind API to insecure port (localhost only)

**Note:** it is needed for [k8s-deployer](../README.md) or you can configure token authentication over secure port
```bash
sed -i 's/--insecure-port=0/--insecure-port=6080/' /etc/kubernetes/manifests/kube-apiserver.yaml
```

All the changes that we just made above will be automatically applied thanks to kubelet service,
though you can restart everything, including kubelet service, if you want to be 100% sure that everything is applied and running as it should

```bash
systemctl stop kubelet
ps aux | grep [k]ube | awk '{print $2}' | xargs kill -9
systemctl start kubelet
```

Provide admin.conf to kubectl

**Note:** don't forget to relogin
```bash
cat > /etc/profile.d/kube.sh <<EOF
#!/bin/bash
export KUBECONFIG=$HOME/admin.conf
EOF
```

Copy admin.conf to home dir of the current user
```bash
cp /etc/kubernetes/admin.conf ${HOME}
```

Add flannel overylay network with required RBAC authorization
```bash
export ARCH="amd64"
kubectl create -f "https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel-rbac.yml"
curl -sSL "https://github.com/coreos/flannel/blob/master/Documentation/kube-flannel.yml?raw=true" | sed "s/amd64/${ARCH}/g" | kubectl create -f -
```

Check if everything is working
```bash
kubectl get nodes -n kube-system -o wide
```


Add additional master or regular node
---

**Note:** replace <token> with token from kubeadm.log file

If you're adding standard node (not a master) you have to execute provided command and
then you must replace API socket (IP:port) in /etc/kubernetes/kubelet.conf config file to floating IP and VS port (172.16.30.30:8443) and restart kubelet service: `systemctl restart kubelet` and that's all you have to do for a regular node
```bash
kubeadm join --token <token> 172.16.30.30:8443
```

On every new regular or master node we must add an iptables rule that will be used for traffic redirection, all traffic intended for the primary master (secure API) will be redirected to LB (floating IP => 172.16.30.30) otherwise if primary master (172.16.30.16) goes down, for any reason, it will be impossible to add (join) any additional/new master or regular nodes in to the cluster, despite the fact that we have a multi-master cluster kubeadm will always try to discover a master node and cluster will always return an IP address of the primary master
```bash
iptables -t nat -A OUTPUT -p tcp -m multiport --dport 6443,8443 -d 172.16.30.16 -j DNAT --to-destination 172.16.30.30:8443
iptables -t nat -L OUTPUT -n -v
```

#### Continue further in this section only if you want to add additional master nodes

Stop kubelet service
```bash
systemctl stop kubelet
```

Copy configuration files and certificates from primary master
```bash
rsync -avP root@172.16.30.16:/etc/kubernetes/ /etc/kubernetes/
```

Replace binding IP for API server

**Note:** primary master has 172.16.30.16 IP and new master has 172.16.30.17 IP
```bash
sed -i 's/--advertise-address=172.16.30.16/--advertise-address=172.16.30.17/' /etc/kubernetes/manifests/kube-apiserver.yaml
```

Start kubelet service and check if all the master services (apiserver, scheduler and controller-manager) are up and running on the new master
```bash
systemctl start kubelet
kubectl get po -o wide -n kube-system
```

Taint master node (disable scheduling of pods on it) and add master label (optional)
```bash
kubectl taint nodes ops-kube-master2 node-role.kubernetes.io/master=:NoSchedule
kubectl label node ops-kube-master2 node-role.kubernetes.io/master=
```


How to fully remove node from the cluster
---

Delete node's data from the datastore (etcd)

**Note:** you can run this command from any node that has kubectl configured
```bash
kubectl drain ${NODE_NAME} --delete-local-data --force --ignore-daemonsets
kubectl delete node ${NODE_NAME}
```

Delete node's local files

**Note:** you must run this command from the node itself
```bash
kubeadm reset
```

Stop and disable kubelet agent
```bash
systemctl disable kubelet
systemctl stop kubelet
```

In some cases you'll maybe have to execute a cleanup of stale containers
```bash
docker rm -f $(docker ps -aq)
```
