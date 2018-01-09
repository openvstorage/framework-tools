#!/bin/bash
# Code to be executed within jenkins for packaging jobs
find ${WORKSPACE} -name *.pyc -exec rm {} \;
find ${WORKSPACE} -name .coverage -exec rm {} \;

PYTHONPATH=:${WORKSPACE}
cd ${WORKSPACE}
ARGS="--product=""${product}"" --release=""${release}"
if [ "${artifact_only}" == "true" ]
then
  ARGS="${ARGS} --artifact-only"
fi
if [ "${no_packaging}" == "true" ]
then
  ARGS="${ARGS} --no-packaging"
fi
if [ -n "${revision}" ] ; then
  ARGS="${ARGS} --revision=""${revision}"" --hotfix-release=""${hotfix_release}"
fi

python packaging/packager.py ${ARGS}

echo "Packaging complete"
