FROM docker.io/library/python@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b
COPY wheels/ /opt/corsair-wheels/
COPY requirements.txt /opt/corsair-wheels/requirements.txt
COPY test_native.py /opt/corsair-fixture/test_native.py
RUN python3.7 -m pip install --no-index --find-links=/opt/corsair-wheels --require-hashes --no-cache-dir -r /opt/corsair-wheels/requirements.txt
ENV HOME=/tmp
USER 10001:10001
