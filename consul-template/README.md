Consul service registration
===

About
---
We'll be using `consul-template` to register kubernetes service as a consul service.
We have four important components, `consul` and `consul-template` binaries, consul template plugin `k8s-svcgen.py` as well as template itself authored in Go template format `k8s-services.ctmpl`


Installation
---
First we have to download `consul` and `consul-template` binaries.

In our environment we're using Chef to download and install `consul` and `consul-template` binaries, nevertheless I will explain here how to do it manually. Also we're using `supervisord` as a process manager so before continue make sure that `supervisord` is installed and configured (http://supervisord.org/), as well as `consul cluster` (https://www.consul.io/docs/guides/manual-bootstrap.html), cause we're going to explain and configure only `consul agent` here.

Also make sure to repeat all these steps on all kubernetes nodes.

**Download consul**

https://www.consul.io/downloads.html

**Download consul-template**

https://releases.hashicorp.com/consul-template

Uncompress and copy binaries to appropriate location
```bash
cp consul consul-template /usr/local/bin
```

Create `consul-template` dir and copy our files into it
```bash
mkdir -p /etc/consul-template/{templates,plugins}
cp k8s-svcgen.py /etc/consul-template/plugins

# Don't forget to change consul template file and to replace key path ('tree' function argument)
# It has to reflect what is defined in k8s-deployer configuration file (config.json) under key_path key + deployments (it's a constant)
# e.g. "key_path": "kubernetes/clustername" => tree "kubernetes/clustername/deployments"
cp k8s-services.ctmpl /etc/consul-template/templates
```

Create `consul` configuration file

**Note:** You have to modify some of these configuration parameters in order to reflect your environment, find out more here https://www.consul.io/docs/agent/options.html
```bash
mkdir -p /etc/consul.d/{agent,services,template}
cat > /etc/consul.d/agent/config.json <<EOF
{
    "data_dir": "/var/lib/consul",
    "advertise_addr": "1.1.1.1",
    "node_name": "k8s-node1.example.com",
    "datacenter": "test1",
    "log_level": "WARN",
    "server": false,
    "rejoin_after_leave": true,
    "encrypt": "DrvFkFc+QwhgHmalwytvHW==",
    "start_join": ["1.1.1.1", "1.1.1.2", "1.1.1.3"],
    "recursors": ["1.1.1.9", "1.1.1.10"]
}
EOF
```

Create `supervisord` configuration files for both services

**Note:** Replace argument of `-consul-addr` option in `consul-template.conf` with real address of your `consul server`
```
cat > /etc/supervisor/conf.d/consul.conf <<EOF
[program:consul]
process_name=%(program_name)s
command=/usr/local/bin/%(program_name)s agent -config-file /etc/consul.d/agent/config.json -config-dir /etc/consul.d/services
directory=/var/lib/consul
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/%(program_name)s-stdout.log
stdout_logfile_maxbytes=100MB
stdout_logfile_backups=10
stdout_capture_maxbytes=1MB
EOF

cat > /etc/supervisor/conf.d/consul-template.conf <<EOF
[program:consul-template]
process_name=%(program_name)s
command=/usr/local/bin/%(program_name)s -consul-addr consul-server.example.com:8500 -template /etc/consul-template/templates/k8s-services.ctmpl:/etc/consul.d/services/k8s-services.json:"/usr/local/bin/supervisorctl signal HUP consul" -log-level info
user=root
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/%(program_name)s-stdout.log
stdout_logfile_maxbytes=100MB
stdout_logfile_backups=10
stdout_capture_maxbytes=1MB
EOF
```

Run services
```bash
supervisorctl reread
supervisorctl update
```

If everything is running smoothly you should see similar output
```bash
supervisorctl status

consul                           RUNNING   pid 28888, uptime 0:00:05
consul-template                  RUNNING   pid 28932, uptime 0:00:04
```

---
Next go to [traefik](../traefik/README.md)
