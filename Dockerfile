# docker build --no-cache -t k8s-deployer .
# docker run -it -d --name k8s-deployer -P k8s-deployer

FROM alpine:3.6

ENV SRV_PORT=8089 \
    PROJECT_DIR=/data/k8s-deployer

WORKDIR $PROJECT_DIR

COPY . ./
RUN apk add --no-cache python py-pip \
 && pip2 install -r requirements.txt \
 && rm -vf requirements.txt

EXPOSE $SRV_PORT

CMD ["/usr/bin/python2", "k8s-deployer.py", "-C", "config.json", "-a", "0.0.0.0"]
