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
    parser.add_option('-a', '--artifact-only', dest='artifact_only', action='store_true', default=False)
    parser.add_option('-u', '--no-upload', dest='no_upload', action='store_true', default=True)
    parser.add_option('-d', '--dry-run', dest='dry_run', action='store_true', default=False)
    parser.add_option('--no-rpm', dest='rpm', action='store_false', default=True)
    parser.add_option('--no-deb', dest='deb', action='store_false', default=True)
    options, args = parser.parse_args()

    print 'Received arguments: {0}'.format(options)
    # 1. Collect sources
    source_collector = SourceCollector(product=options.product,
                                       release=options.release,
                                       revision=options.revision,
                                       artifact_only=options.artifact_only,
                                       dry_run=options.dry_run)
    # Setting it to artifact only also means no uploading
    if options.artifact_only is True:
        options.no_upload = True
    settings = source_collector.settings
    metadata = source_collector.collect()
    print 'Package metadata: {0}'.format(metadata)

    if metadata is not None:
        add_package = options.release != 'hotfix'
        # 2. Build & Upload packages
        if options.deb is True and 'deb' not in settings['repositories']['exclude_builds'].get(options.product, []):
            debian_packager = DebianPackager(source_collector=source_collector,
                                             dry_run=options.dry_run)
            debian_packager.package()
            try:
                if options.no_upload is False:
                    debian_packager.upload(add=add_package, hotfix_release=options.hotfix_release)
            finally:
                # Always store artifacts in jenkins too
                debian_packager.prepare_artifact()
                DebianPackager.prepare_artifact(metadata)
        if options.rpm is True and 'rpm' not in settings['repositories']['exclude_builds'].get(options.product, []):
            rpm_packager = RPMPackager(source_collector=source_collector,
                                       dry_run=options.dry_run)
            rpm_packager.package()
            if options.no_upload is False:
                rpm_packager.upload()  # add not relevant for RPM
