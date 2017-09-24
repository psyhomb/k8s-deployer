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
__version__ = 'v0.1.2'
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
        try:
            with open(config_file, 'rU') as f:
                config = json.load(f)
        except ValueError:
            print('Wrong JSON format in {} file'.format(config_file))
            sys.exit(3)
        except IOError as e:
            print('Error while reading from file, {}'.format(e))
            sys.exit(2)
        else:
            return config
    else:
        print('Configuration file {} not found'.format(config_file))
        sys.exit(1)


def req(method, url, headers={}, payload=None, status_code=False):
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
                    method, url, headers=pass_headers, verify=False
                )
        elif method in ['POST', 'PUT', 'PATCH']:
            ### built-in json parameter does not support pretty-printing
            # r = requests.request(method, url, json=payload)
            r = requests.request(
                    method, url, headers=pass_headers, verify=False,
                    data=json.dumps(
                        payload, indent=4, separators=(',', ': ')
                    )
                )

        if status_code:
            if r.status_code == 200:
                return {
                    'status_code': r.status_code,
                    'payload': r.json()
                }

            return {
                'status_code': r.status_code,
                'payload': {}
            }

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
                                'type': 'object',
                                'properties': {
                                    'kind': {
                                        'type': ['string']
                                    }
                                }
                            }
                        }
                    },
                    'services': {
                        'type': 'object',
                        'properties': {
                            'specification': {
                                'type': 'object',
                                'properties': {
                                    'kind': {
                                        'type': ['string']
                                    }
                                }
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
        abort(422, 'Only services of type NodePort are supported')

    return svc


def create_object(k8s_host, **kwargs):
    """
    Create deployment and service objects on Kubernetes (output: list)
    """
    pass_headers = {}
    if 'k8s_api_headers' in kwargs:
        headers = kwargs.pop('k8s_api_headers')

    pass_headers.update(headers)

    namespace = kwargs['namespace']
    objects = kwargs['objects']

    svcs = []
    for obj in objects:
        api_path = K8S_API[obj]
        url = '{}/{}/namespaces/{}/{}'.format(
                    k8s_host, api_path,
                    namespace, obj
                )

        if objects[obj]['specification']['kind'] == 'List':
            specs = objects[obj]['specification']['items']
        else:
            specs = [objects[obj]['specification']]

        for spec in specs:
            payload = req('POST', url, pass_headers, payload=spec)
            if obj == 'services':
                svcs.append(payload)

    return svcs


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
    specs = kwargs['objects']['deployments']['specification']

    if specs['kind'] == 'List':
        deployments = specs['items']
    else:
        deployments = [specs]

    for deployment in deployments:
        deployment_name = deployment['metadata']['name']
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

    obj_names = []
    for obj in objects:
        if objects[obj]['specification']['kind'] == 'List':
            specs = objects[obj]['specification']['items']
        else:
            specs = [objects[obj]['specification']]

        for spec in specs:
            if obj == 'deployments':
                rs_label_selector = spec['spec']['selector']['matchLabels']
                labels = ','.join(
                        [ '{}={}'.format(k, v)  for k, v in rs_label_selector.items() ]
                    )
                url = '{}/{}/namespaces/{}/{}/?labelSelector={}'.format(
                        k8s_host, K8S_API['replicasets'],
                        namespace, 'replicasets',
                        labels
                    )
                obj_names.append({
                    'deployments': spec['metadata']['name'],
                    'replicasets': req('GET', url)['items'][0]['metadata']['name']
                })
            else:
                obj_names.append({
                    'services': spec['metadata']['name'],
                })

    for d in obj_names:
        for obj, obj_name in d.items():
            url = '{}/{}/namespaces/{}/{}/{}'.format(
                        k8s_host, K8S_API[obj],
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

    # Kubernetes related env vars
    if os.environ.get('K8S_DEPLOYER_KUBE_SCHEME'):
        config['kubernetes']['scheme'] = (
            os.environ['K8S_DEPLOYER_KUBE_SCHEME']
        )
    if os.environ.get('K8S_DEPLOYER_KUBE_HOST'):
        config['kubernetes']['host'] = (
            os.environ['K8S_DEPLOYER_KUBE_HOST']
        )
    if os.environ.get('K8S_DEPLOYER_KUBE_PORT'):
        config['kubernetes']['port'] = (
            os.environ['K8S_DEPLOYER_KUBE_PORT']
        )
    if os.environ.get('K8S_DEPLOYER_KUBE_API_HEADERS'):
        # K8S_DEPLOYER_KUBE_API_HEADERS="User-Agent__test,Host__example.com"
        for h in os.environ.get('K8S_DEPLOYER_KUBE_API_HEADERS').split(','):
            for k, v in [h.strip().split('__')]:
                config['kubernetes']['api']['headers'][k] = v

    # Consul related env vars
    if os.environ.get('K8S_DEPLOYER_CONSUL_SCHEME'):
        config['consul']['scheme'] = (
            os.environ['K8S_DEPLOYER_CONSUL_SCHEME']
        )
    if os.environ.get('K8S_DEPLOYER_CONSUL_HOST'):
        config['consul']['host'] = (
            os.environ['K8S_DEPLOYER_CONSUL_HOST']
        )
    if os.environ.get('K8S_DEPLOYER_CONSUL_PORT'):
        config['consul']['port'] = (
            os.environ['K8S_DEPLOYER_CONSUL_PORT']
        )
    if os.environ.get('K8S_DEPLOYER_CONSUL_KEY_PATH'):
        config['consul']['key_path'] = (
            os.environ['K8S_DEPLOYER_CONSUL_KEY_PATH']
        )
    if os.environ.get('K8S_DEPLOYER_CONSUL_SPECS_RETENT'):
        config['consul']['specifications']['retention'] = (
            os.environ['K8S_DEPLOYER_CONSUL_SPECS_RETENT']
        )

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
        """
        Show all available specifications from Consul K/V store
        """
        spec_key = '{}/specifications'.format(consul_key_path)

        if namespace is None:
            payload = get_kv(consul_host, spec_key, list_keys=True)
        elif namespace is not None and service_name is None:
            spec_key += '/{}'.format(namespace)
            payload = get_kv(consul_host, spec_key, list_keys=True)
        elif service_name is not None and service_id is None:
            spec_key += '/{}/{}'.format(namespace, service_name)
            payload = get_kv(consul_host, spec_key, list_keys=True)
        else:
            spec_key += '/{}/{}/{}'.format(namespace, service_name, service_id)
            payload = get_kv(consul_host, spec_key)

        return {'specifications': payload}


    @post('/specifications/<namespace>/<service_name>')
    def insert_spec(namespace, service_name):
        """
        Insert provided specification into the Consul K/V store
        and do rotations of stale specifications per retention value
        """
        response.status = 201

        payload = request.json
        spec_validator(payload)

        service_id = '{:.0f}_{}'.format(time.time() * 10**6, uuid4())
        payload['id'] = service_id
        payload['namespace'] = namespace
        spec_key = '{}/specifications/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )

        for key in [service_id, 'latest']:
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
        """
        Create service and deployment objects on Kubernetes
        and insert retrieved service data into the Consul K/V store
        """
        spec_key = '{}/specifications/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )
        svc_key = '{}/deployments/{}'.format(
                        consul_key_path, namespace
                    )

        payload = get_kv(consul_host, '{}/{}'.format(spec_key, service_id))
        spec_validator(payload)

        svcs = create_object(
                    k8s_host, k8s_api_headers=k8s_api_headers, **payload
                )
        for svc in svcs:
            create_kv(
                consul_host,
                '{}/{}'.format(svc_key, svc['metadata']['name']),
                svc
            )
        create_kv(consul_host, spec_key + '/deployed', payload)

        return {'services': svcs}


    @put('/registration/<namespace>/<service_name>')
    def insert_svc(namespace, service_name):
        """
        Fetch service definition for specified service from Kubernetes
        and populate Consul K/V store with received data
        """
        svc_key = '{}/deployments/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )

        svc = fetch_svc(
                k8s_host,
                k8s_api_headers=k8s_api_headers,
                namespace=namespace,
                service_name=service_name
            )
        create_kv(consul_host, svc_key, svc)

        return svc


    @delete('/deployments/<namespace>/<service_name>')
    def delete_svc(namespace, service_name):
        """
        Delete all related Kubernetes objects for specified service
        and remove Consul keys from specifications and deployments tree
        """
        response.status = 204

        spec_key = '{}/specifications/{}/{}'.format(
                        consul_key_path, namespace, service_name
                    )
        svc_key = '{}/deployments/{}'.format(
                        consul_key_path, namespace
                    )

        payload = get_kv(consul_host, '{}/{}'.format(spec_key, 'deployed'))
        spec_validator(payload)

        # Consul
        # Delete specs
        delete_kv(consul_host, spec_key + '/deployed')
        specs = payload['objects']['services']['specification']
        if specs['kind'] == 'List':
            for spec in specs['items']:
                delete_kv(
                    consul_host,
                    '{}/{}'.format(svc_key, spec['metadata']['name'])
                )
        else:
            delete_kv(
                consul_host,
                '{}/{}'.format(svc_key, specs['metadata']['name'])
            )

        # Kubernetes
        # Terminate all running pods (scale down to 0)
        scale_down(k8s_host, k8s_api_headers=k8s_api_headers, **payload)
        # Delete all related objects
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
