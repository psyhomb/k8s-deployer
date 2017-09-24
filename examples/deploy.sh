#!/bin/bash

K8S_DEPLOYER_HOST="localhost:8089"

SPEC_ID=$(curl -X POST -isSL -H 'Content-Type: application/json' --data '@echoserver.json' http://${K8S_DEPLOYER_HOST}/specifications/default/echoserver | awk -F'/' '/^Location:/ {print $(NF-1)"/"$NF}' | tr -d '\r')
curl -X PUT -isSL http://${K8S_DEPLOYER_HOST}/deployments/default/${SPEC_ID}
