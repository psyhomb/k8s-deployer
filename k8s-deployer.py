#!/usr/bin/env python2

import sys
import os
import json
import argparse
import requests
import time
import validictory
from base64 import b64decode
from uuid import uuid4
from bottle import get, post, put, delete, abort, request, response, run


__prog__ = os.path.splitext(os.path.basename(__file__))[0]
__version__ = 'v0.1'
__author__ = 'Milos Buncic'
__date__ = '2017/03/20'
__description__ = 'Kubernetes deployer API with Consul registration'


# Kubernetes API groups and versions
K8S_API = {
    'services': 'api/v1',
    'deployments': 'apis/apps/v1beta1',
    'replicasets': 'apis/extensions/v1beta1'
}

# Consul key/value API
CONSUL_KV_API = 'v1/kv'


def load_config(config_file):
    """
    Load configuration from file (output: dict)
    """
    if os.path.isfile(config_file):
        with open(config_file, 'rU') as f:
            config = json.load(f)
    else:
        print('File {} not found'.format(config_file))
        sys.exit(1)

    return config


def req(method, url, headers={}, payload=None):
    """
    Request function with error handlers (output: dict)
    """
    pass_headers = {}
    const_headers = {
        'User-Agent': '{}/{}'.format(
                __prog__, __version__
            )
    }
    pass_headers.update(headers)
    pass_headers.update(const_headers)

    try:
        if method in ['GET', 'DELETE']:
            r = requests.request(
                    method, url, headers=pass_headers,
                    verify=False
                )
        elif method in ['POST', 'PUT', 'PATCH']:
            ### built-in json parameter does not support pretty-printing
            # r = requests.request(method, url, json=payload)
            r = requests.request(
                    method, url, headers=pass_headers,
                    data=json.dumps(payload, indent=4),
                    verify=False
                )
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        abort(r.status_code, 'HTTPError: {}'.format(e))
    except requests.exceptions.ConnectionError as e:
        abort(504, 'ConnectionError: {}'.format(e))

    return r.json()


def spec_validator(data):
    """
    Validate JSON data
    """
    schema = {
        'type': 'object',
        'properties': {
            'id': {
                'type': ['null', 'string']
            },
            'namespace': {
                'type': ['null', 'string']
            },
            'objects': {
                'type': 'object',
                'properties': {
                    'deployments': {
                        'type': 'object',
                        'properties': {
                            'specification': {
                                'type': 'object'
                            }
                        }
                    },
                    'services': {
                        'type': 'object',
                        'properties': {
                            'specification': {
                                'type': 'object'
                            }
                        }
                    }
                },
                "additionalProperties": False
            }
        },
        "additionalProperties": False
    }

    try:
        validictory.validate(data, schema)
    except ValueError as e:
        abort(422, 'Bad JSON schema: {}'.format(e))


def fetch_svc(k8s_host, **kwargs):
    """
    Fetch named service definition from Kubernetes (output: dict)
    """
    pass_headers = {}
    if 'k8s_api_headers' in kwargs:
        headers = kwargs.pop('k8s_api_headers')

    pass_headers.update(headers)

    namespace = kwargs['namespace']
    service_name = kwargs['service_name']

    url = '{}/{}/namespaces/{}/{}/{}'.format(
                k8s_host, K8S_API['services'],
                namespace, 'services', service_name
            )
    svc = req('GET', url, pass_headers)

    if svc['spec']['type'] != 'NodePort':
        abort(422, 'Only services with type NodePort are supported')

    return svc


def create_object(k8s_host, **kwargs):
    """
    Create deployment and service objects on Kubernetes (output: dict)
    """
    pass_headers = {}
    if 'k8s_api_headers' in kwargs:
        headers = kwargs.pop('k8s_api_headers')

    pass_headers.update(headers)

    namespace = kwargs['namespace']
    objects = kwargs['objects']

    for obj in objects:
        api_path = K8S_API[obj]
        url = '{}/{}/namespaces/{}/{}'.format(
                    k8s_host, api_path,
                    namespace, obj
                )
        spec = objects[obj]['specification']

        payload = req('POST', url, pass_headers, payload=spec)
        if obj == 'services':
            svc = payload

    return svc


def scale_down(k8s_host, **kwargs):
    """
    Scale down number of replicas to 0
    """
    pass_headers = {}
    if 'k8s_api_headers' in kwargs:
        headers = kwargs.pop('k8s_api_headers')

    pass_headers.update(headers)
    pass_headers.update({
        'Content-Type': 'application/strategic-merge-patch+json'
    })
    payload = {
        'spec': {
            'replicas': 0
        }
    }
    api_path = K8S_API['deployments']
    namespace = kwargs['namespace']
    deployment_name = (kwargs['objects']['deployments']
           ['specification']['metadata']['name']
        )

    url = '{}/{}/namespaces/{}/deployments/{}'.format(
                k8s_host, api_path,
                namespace,
                deployment_name
            )

    req('PATCH', url, pass_headers, payload)


def delete_object(k8s_host, **kwargs):
    """
    Delete deployment and service objects from Kubernetes
    """
    pass_headers = {}
    if 'k8s_api_headers' in kwargs:
        headers = kwargs.pop('k8s_api_headers')

    pass_headers.update(headers)

    namespace = kwargs['namespace']
    objects = kwargs['objects']

    for obj in objects.keys() + ['replicasets']:
        api_path = K8S_API[obj]
        if obj == 'replicasets':
            rs_label_selector = (kwargs['objects']['deployments']
                    ['specification']['spec']['selector']['matchLabels']
                )
            labels = ','.join(
                    [ '{}={}'.format(k, v)  for k, v in rs_label_selector.items() ]
                )
            url = '{}/{}/namespaces/{}/{}/?labelSelector={}'.format(
                    k8s_host, api_path,
                    namespace, obj,
                    labels
                )
            obj_name = req('GET', url)['items'][0]['metadata']['name']
        else:
            obj_name = (kwargs['objects']['services']
                        ['specification']['metadata']['name']
                    )

        url = '{}/{}/namespaces/{}/{}/{}'.format(
                    k8s_host, api_path,
                    namespace, obj, obj_name
                )

        req('DELETE', url, pass_headers)


def get_kv(consul_host, key, list_keys=False):
    """
    Retrieve value for specified key from Consul (output: dict or list)
    """
    url = '{}/{}/{}'.format(consul_host, CONSUL_KV_API, key)

    if list_keys:
        value = req('GET', url + '/?keys')
    else:
        try:
            value = json.loads(b64decode(req('GET', url)[0]['Value']))
        except ValueError as e:
            abort(422, 'Bad JSON: {}'.format(e))

    return value


def create_kv(consul_host, key, value):
    """
    Create key/value pair on Consul
    """
    url = '{}/{}/{}'.format(consul_host, CONSUL_KV_API, key)

    req('PUT', url, payload=value)


def delete_kv(consul_host, key):
    """
    Delete specified key or list of keys from Consul
    """
    if type(key) is str:
        key = [key]

    for k in key:
        url = '{}/{}/{}'.format(consul_host, CONSUL_KV_API, k)
        req('DELETE', url)


def main():
    parser = argparse.ArgumentParser(
                formatter_class=argparse.ArgumentDefaultsHelpFormatter
            )
    parser.add_argument(
        '-C', '--config',
        help='Path to the configuration file',
        dest='config',
        action='store',
        required=True
    )

    parser.add_argument(
        '-a', '--bind-addr',
        help='Web server bind IP',
        default='127.0.0.1',
        dest='bind_addr',
        action='store'
    )

    parser.add_argument(
        '-p', '--bind-port',
        help='Web server bind port',
        default=8089,
        type=int,
        dest='bind_port',
        action='store'
    )

    parser.add_argument(
        '-w', '--workers',
        help='Number of web server workers',
        default=5,
        type=int,
        dest='workers',
        action='store'
    )

    args = parser.parse_args()

    bind_addr = args.bind_addr
    bind_port = args.bind_port
    workers = args.workers
    config = load_config(args.config)

    k8s_host = '{}://{}:{}'.format(
            config['kubernetes']['scheme'],
            config['kubernetes']['host'],
            config['kubernetes']['port']
        )
    k8s_api_headers = config['kubernetes']['api']['headers']
    consul_host = '{}://{}:{}'.format(
            config['consul']['scheme'],
            config['consul']['host'],
            config['consul']['port']
        )
    consul_key_path = config['consul']['key_path']
    spec_retention = config['consul']['specifications']['retention']


    @get('/specifications')
    @get('/specifications/<namespace>')
    @get('/specifications/<namespace>/<service_name>')
    @get('/specifications/<namespace>/<service_name>/<service_id>')
    def show_spec(namespace=None, service_name=None, service_id=None):
        response.content_type = 'application/json; charset=UTF-8'

        spec_key = '{}/specifications'.format(consul_key_path)
        if namespace is None:
            payload = json.dumps(get_kv(consul_host, spec_key, list_keys=True))
        elif namespace is not None and service_name is None:
            spec_key += '/{}'.format(namespace)
            payload = json.dumps(get_kv(consul_host, spec_key, list_keys=True))
        elif service_name is not None and service_id is None:
            spec_key += '/{}/{}'.format(namespace, service_name)
            payload = json.dumps(get_kv(consul_host, spec_key, list_keys=True))
        else:
            spec_key += '/{}/{}/{}'.format(namespace, service_name, service_id)
            payload = json.dumps(get_kv(consul_host, spec_key))

        return payload


    @post('/specifications')
    @post('/specifications/<namespace>')
    def insert_spec(namespace='default'):
        response.status = 201

        payload = request.json
        spec_validator(payload)

        payload['namespace'] = namespace
        service_name = (payload['objects']['services']
                ['specification']['metadata']['name']
            )
        service_id = '{:.0f}_{}'.format(time.time() * 10**6, uuid4())
        spec_key = '{}/specifications/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )

        for key in [service_id, 'latest']:
            if key == 'latest':
                payload['id'] = service_id
            create_kv(consul_host, '{}/{}'.format(spec_key, key), payload)

        response.add_header('Location', '{}/{}'.format(spec_key, service_id))

        # Cleanup
        spec_revs = get_kv(consul_host, spec_key, list_keys=True)
        for p in ['/latest', '/deployed']:
            preserve = spec_key + p
            if preserve in spec_revs:
                spec_revs.remove(preserve)

        stale_revs = sorted(spec_revs)[:-spec_retention]
        delete_kv(consul_host, stale_revs)


    @put('/deployments/<namespace>/<service_name>')
    @put('/deployments/<namespace>/<service_name>/<service_id>')
    def deploy_spec(namespace, service_name, service_id='latest'):
        spec_key = '{}/specifications/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )
        payload = get_kv(consul_host, '{}/{}'.format(spec_key, service_id))
        spec_validator(payload)

        svc_key = '{}/deployments/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )
        svc = create_object(
                    k8s_host, k8s_api_headers=k8s_api_headers, **payload
                )

        create_kv(consul_host, svc_key, svc)
        create_kv(consul_host, spec_key + '/deployed', payload)

        return svc


    @put('/registration/<namespace>/<service_name>')
    def insert_svc(namespace, service_name):
        """
        Fetch service definition for named service from Kubernetes
        and populate Consul key/value store with recieved data
        """
        svc = fetch_svc(
                    k8s_host,
                    k8s_api_headers=k8s_api_headers,
                    namespace=namespace,
                    service_name=service_name
                )

        svc_key = '{}/deployments/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )
        create_kv(consul_host, svc_key, svc)

        return svc


    @delete('/deployments/<namespace>/<service_name>')
    def delete_svc(namespace, service_name):
        response.status = 204

        svc_key = '{}/deployments/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )
        # service_id = get_kv(consul_host, svc_key)['id']

        spec_key = '{}/specifications/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )
        payload = get_kv(consul_host, '{}/{}'.format(spec_key, 'latest'))

        # Delete all running pods (scale down to 0)
        scale_down(k8s_host, k8s_api_headers=k8s_api_headers, **payload)
        # Delete specs from Consul
        for key in [spec_key + '/deployed', svc_key]:
            delete_kv(consul_host, key)
        # Delete Kubernetes objects
        delete_object(k8s_host, k8s_api_headers=k8s_api_headers, **payload)


    run(
        host=bind_addr,
        port=bind_port,
        server='paste',
        use_threadpool=True,
        threadpool_workers=workers
    )


if __name__ == '__main__':
    main()
