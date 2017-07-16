#!/usr/bin/env python2
# Author: Milos Buncic
# Date: 2016/03/30
# Description: Generates Consul service definition
#
# Consul template k8s-services.ctmpl:
#
#     {{- tree "kubernetes/deployments" | explode | toJSON | plugin "./k8s-svcgen.py" -}}
#
# Generate k8s-services.json file using consul template:
#
#     consul-template \
#         -consul-addr consul.example.com:8500 \
#         -template k8s-services.ctmpl:k8s-services.json \
#         -once
#
# Now, restart the agent, providing the configuration directory:
#
#     $ consul agent -dev -config-dir=/etc/consul.d
#     ==> Starting Consul agent...
#     ...
#     [INFO] agent: Synced service 'svc1'
#     ...

import sys, json

args = sys.argv
data = args[1]

svcs = []

if data:
    d = json.loads(data)

    for ns in d.values():
        for s in ns.values():
            svc = json.loads(s)

            name = svc['metadata']['name']
            annotations = svc['metadata'].get('annotations')
            node_port = svc['spec']['ports'][0]['nodePort']

            if annotations is None:
                tags = None
            else:
                tags = []
                for k,v in annotations.items():
                    constraint = k.split('.')[0]
                    if constraint == 'traefik':
                        tags.append('{}={}'.format(k,v))
                    elif constraint == 'tags':
                        tags += [  tag.strip()  for tag in v.split(',')  ]

            svcs.append({
                'name': name,
                'tags': tags,
                'port': node_port
            })

    services = {'services': svcs}
    print(json.dumps(services, indent=2))
