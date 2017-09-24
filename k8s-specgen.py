#!/usr/bin/env python2
# Author: Milos Buncic
# Date: 2017/09/17
# Description: Generates k8s-deployer specification file

import os
import sys
import json
import argparse


def write_to_file(filename, data):
    """
    Write data to file
    """
    if not os.path.exists(filename):
        try:
            with open(filename, 'w') as f:
                f.write(json.dumps(
                        data, indent=4, separators=(',', ': '),
                        ensure_ascii=False, sort_keys=True
                    ).encode('utf-8')
                )
            print('File {} has been successfully created'.format(filename))
        except IOError as e:
            print('Error while writing to file, {}'.format(e))
            sys.exit(2)
    else:
       print('File {} already exists'.format(filename))
       sys.exit(1)


def read_from_file(filename):
    """
    Read data from file (output: dict)
    """
    try:
        with open(filename, 'rU') as f:
            return json.load(f)
    except ValueError:
        print('Wrong JSON format in {} file'.format(filename))
        sys.exit(3)
    except IOError as e:
        print('Error while reading from file, {}'.format(e))
        sys.exit(2)


def spec_gen(deploy={}, service={}):
    """
    Generate k8s-deployer specification file
    """
    spec = {
        'id': None,
        'namespace': None,
        'objects': {
            'deployments': {
                'specification': {}
            },
            'services': {
                'specification': {}
            }
        }
    }

    spec['objects']['deployments']['specification'] = deploy
    spec['objects']['services']['specification'] = service

    return spec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-d', '--deploy',
        help='Kubernetes deployment specification file in json format',
        dest='deploy',
        action='store',
        required=True
    )

    parser.add_argument(
        '-s', '--service',
        help='Kubernetes service specification file in json format',
        dest='service',
        action='store',
        required=True
    )

    parser.add_argument(
        '-o', '--output',
        help='k8s-deployer specification file',
        dest='spec',
        action='store',
        required=True
    )

    args = parser.parse_args()

    deploy = read_from_file(args.deploy)
    service = read_from_file(args.service)

    write_to_file(args.spec, spec_gen(deploy, service))


if __name__ == '__main__':
    main()
