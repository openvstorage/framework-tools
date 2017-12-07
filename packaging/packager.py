# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
Packager module
"""

import os
from optparse import OptionParser
from sourcecollector import SourceCollector
from debian import DebianPackager
from redhat import RPMPackager


if __name__ == '__main__':
    parser = OptionParser(description='Open vStorage packager')
    parser.add_option('-p', '--product', dest='product')
    parser.add_option('-r', '--release', dest='release', default=None)
    parser.add_option('-e', '--revision', dest='revision', default=None)
    parser.add_option('-o', '--hotfix-release', dest='hotfix_release', default=None)
    parser.add_option('-a', '--artifact-only', dest='artifact_only', default=False)
    parser.add_option('--no-rpm', dest='rpm', action='store_false', default=True)
    parser.add_option('--no-deb', dest='deb', action='store_false', default=True)
    options, args = parser.parse_args()

    # 1. Collect sources
    settings = SourceCollector.json_loads('{0}/{1}'.format(os.path.dirname(os.path.realpath(__file__)), 'settings.json'))
    metadata = SourceCollector.collect(product=options.product,
                                       release=options.release,
                                       revision=options.revision,
                                       artifact_only=options.artifact_only)

    if metadata is not None:
        add_package = options.release != 'hotfix'
        # 2. Build & Upload packages
        if options.deb is True and 'deb' not in settings['repositories']['exclude_builds'].get(options.product, []):
            DebianPackager.package(metadata)
            if options.artifact_only is False:
                DebianPackager.upload(metadata, add=add_package, hotfix_release=options.hotfix_release)
            # Always store artifacts in jenkins too
            DebianPackager.prepare_artifact(metadata)
        if options.rpm is True and 'rpm' not in settings['repositories']['exclude_builds'].get(options.product, []):
            RPMPackager.package(metadata)
            if options.artifact_only is False:
                RPMPackager.upload(metadata)  # add not relevant for RPM
