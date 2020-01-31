FROM python:3.8

RUN curl -L https://storage.googleapis.com/kubernetes-release/release/v1.16.0/bin/linux/amd64/kubectl > /usr/local/bin/kubectl
RUN chmod +x /usr/local/bin/kubectl

COPY . /srv/kubessh
COPY helm-chart/images/kubessh/kubessh_config.py /srv/kubessh

WORKDIR /srv/kubessh

RUN pip3 install --no-cache-dir .

ENTRYPOINT [ "/usr/local/bin/kubessh" ]