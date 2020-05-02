FROM python:3.8

RUN set -x \
  &&  curl -L https://storage.googleapis.com/kubernetes-release/release/v1.16.0/bin/linux/amd64/kubectl > /usr/local/bin/kubectl \
  && chmod +x /usr/local/bin/kubectl

RUN set -x \
  && mkdir -vp /usr/local/share/kubessh \
  && curl -L https://github.com/mvoelske/static-openssh-sftp-server/releases/download/v0.1.0/sftp-server > /usr/local/share/kubessh/sftp-server \
  && chmod +x /usr/local/share/kubessh/sftp-server

COPY . /srv/kubessh
COPY helm-chart/images/kubessh/kubessh_config.py /srv/kubessh

WORKDIR /srv/kubessh

RUN pip3 install --no-cache-dir .

ENTRYPOINT [ "/usr/local/bin/kubessh" ]
