k8s-deployer HTTP API
===


About
---
Deploy Kubernetes service and insert retrieved information into Consul K/V store


Installation
---
#### Supervisor
Install pew (python environment wrapper)
```bash
pip2 install pew
```

Create required project dirs
```bash
mkdir -p /data/pew/virtualenvs
mkdir -p /etc/k8s-deployer
mkdir -p /var/log/k8s-deployer
```

Clone repo
```bash
git clone https://<fqdn>/<username>/k8s-deployer.git /data/pew/k8s-deployer
cd /data/pew/k8s-deployer
```

Create a new virtualenv for `k8s-deployer` project
```bash
WORKON_HOME="/data/pew/virtualenvs" pew new -a /data/pew/k8s-deployer -r requirements.txt k8s-deployer
```

Enter virtualenv (previous commad will also enter virtualenv at the end)
```bash
WORKON_HOME=/data/pew/virtualenvs pew workon k8s-deployer
```

Copy and modify `k8s-deployer` configuration file
```bash
cp /data/pew/k8s-deployer/config.json /etc/k8s-deployer/config.json
```

Copy and modify supervisor configuration file
```bash
cp /data/pew/k8s-deployer/supervisor/k8s-deployer.conf /etc/supervisor/conf.d/k8s-deployer.conf
```

Add and start service
```
supervisorctl reread
supervisorctl add k8s-deployer
```

#### Docker
Build and run
```
docker build --no-cache -t k8s-deployer:0.1 .
docker run -it -d --name k8s-deployer -p 8089:8089 k8s-deployer:0.1
```


Usage
---
For quick test deploy you can use `deploy.sh` script located in examples dir, in this dir you will also find `echoserver.json` specification descriptor that will be used for deploying the `echoserver` service.

```bash
cd examples
./deploy.sh
```

Specification descriptor:
```json
{
    "id": null,
    "namespace": null,
    "objects": {
        "deployments": {
            "api_path": "apis/extensions/v1beta1",
            "specification": {
                "### Kubernetes deployment object spec goes here"
            }
        },
        "services": {
            "api_path": "api/v1",
            "specification": {
                "### Kubernetes service object spec goes here"
            }
        }
    }
}
```

If you already have `yaml` spec files you can use `kubectl` to convert these locally to `json` format.
```bash
kubectl convert -f echoserver-deployment.yaml --local -o json
kubectl convert -f echoserver-service.yaml --local -o json
```

Kubernetes documentation regarding deployment and service objects

https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

https://kubernetes.io/docs/concepts/services-networking/service/

Kubernetes API references

https://kubernetes.io/docs/reference/

---

Insert specification for a new service into Consul K/V store

**Note:** by default max 5 specifications for the same service will be held in the Consul K/V store (you can modify this value in the configuration file)

**Note:** after successful transaction specification id will be returned as `Location` header value
```bash
curl -X POST -isSL -H 'Content-Type: application/json' --data '@echoserver.json' http://localhost:8089/specifications/default
```
or (default namespace value is `default` that's why we can omit namespace in URL path, unless we don't want to deploy a service in some other namespace)
```bash
curl -X POST -isSL -H 'Content-Type: application/json' --data '@echoserver.json' http://localhost:8089/specifications
```

List all available specification ids
```bash
curl -isSL http://localhost:8089/specifications/default/echoserver
```

Show service specification
```bash
curl -isSL http://localhost:8089/specifications/default/echoserver/latest
```

Deploy a new service using specification previously inserted into Consul K/V store

**Note:** if we don't specify an id, `latest` specification will be used

**Note:** after every successful build `deployed` spec will be created in the `kubernetes/specifications/<namespace>/<servicename>` tree
```bash
curl -X PUT -isSL http://localhost:8089/deployments/default/echoserver
```
or you can explicitly set specification id
```bash 
curl -X PUT -isSL http://localhost:8089/deployments/default/echoserver/1490691025506482_1650b288-e79c-4247-9b3b-95f1051302c4
```

Undeploy service

**Note:** it's going to delete service from Kubernetes and service definition from Consul K/V store
```
curl -X DELETE -isSL http://localhost:8089/deployments/default/echoserver
```
