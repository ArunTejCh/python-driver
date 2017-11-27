#!/bin/bash
set -e -x

# Install a system package required by our library
wget http://repository.it4i.cz/mirrors/repoforge/redhat/el5/en/x86_64/rpmforge/RPMS/rpmforge-release-0.5.3-1.el5.rf.x86_64.rpm
rpm -i rpmforge*
yum install -y libev libev-devel

mkdir wheelhouse
EXCLUDED_PY_VERS=( cp26 cp33 cp34 cp35 cp27 cpython-2.6 )

ls /opt/python/
# Compile wheels
for PYBIN in /opt/python/cp36-cp36m/bin; do
   for PY_VER in "${EXCLUDED_PY_VERS[@]}"; do
       if [[ "${PYBIN}" == *"$PY_VER"* ]]; then
          echo "In excluded python version. Skipping $PY_VER"
          continue 2
          fi
    done
    "${PYBIN}/pip" install -r /io/requirements.txt
    "${PYBIN}/pip" wheel /io/ -w wheelhouse/
done

# Bundle external shared libraries into the wheels
for whl in wheelhouse/*cassandra_driver*.whl; do
   auditwheel repair "$whl" -w /io/wheelhouse/
done

