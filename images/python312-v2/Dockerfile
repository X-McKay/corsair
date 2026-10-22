FROM docker.io/library/python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d
COPY wheels/ /opt/corsair-wheels/
COPY requirements.txt /opt/corsair-wheels/requirements.txt
COPY test_native.py /opt/corsair-fixture/test_native.py
RUN python3.12 -m pip install --no-index --find-links=/opt/corsair-wheels --require-hashes --no-cache-dir -r /opt/corsair-wheels/requirements.txt
ENV HOME=/tmp
USER 10001:10001
