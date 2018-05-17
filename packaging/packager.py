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
from packaging.packagers.debian import DebianPackager
from packaging.packagers.redhat import RPMPackager
from packaging.packagers.pip import PIPDebianPackager


if __name__ == '__main__':
    parser = OptionParser(description='Open vStorage packager')
    parser.add_option('-p', '--product', dest='product')
    parser.add_option('-r', '--release', dest='release', default=None)
    parser.add_option('-e', '--revision', dest='revision', default=None)
    parser.add_option('-o', '--hotfix-release', dest='hotfix_release', default=None)
    parser.add_option('-a', '--artifact-only', dest='artifact_only', action='store_true', default=False)
    parser.add_option('-u', '--no-upload', dest='no_upload', action='store_true', default=False)
    parser.add_option('-d', '--dry-run', dest='dry_run', action='store_true', default=False)
    parser.add_option('--no-rpm', dest='rpm', action='store_false', default=True)
    parser.add_option('--no-deb', dest='deb', action='store_false', default=True)
    parser.add_option('--pip', dest='is_pip', action='store_true', default=False)
    options, args = parser.parse_args()

    print 'Received arguments: {0}'.format(options)
    # 1. Collect sources
    source_collector = SourceCollector(product=options.product,
                                       release=options.release,
                                       revision=options.revision,
                                       artifact_only=options.artifact_only,
                                       dry_run=options.dry_run,
                                       is_pip=options.is_pip)
    # Setting it to artifact only also means no uploading
    if options.artifact_only is True:
        options.no_upload = True
    settings = source_collector.settings
    metadata = source_collector.collect()
    print 'Package metadata: {0}'.format(metadata)

    if metadata is not None:
        add_package = options.release != 'hotfix'
        # 2. Build & Upload packages
        packagers = []
        if any(option is True for option in [options.deb, options.rpm]):
            if options.deb is True and 'deb' not in settings['repositories']['exclude_builds'].get(options.product, []):
                packagers.append(DebianPackager(source_collector=source_collector, dry_run=options.dry_run))
            if options.rpm is True and 'rpm' not in settings['repositories']['exclude_builds'].get(options.product, []):
                packagers.append(RPMPackager(source_collector=source_collector, dry_run=options.dry_run))
        elif options.pip is True and options.product in settings['pip']['modules']:
            packagers.append(PIPDebianPackager(source_collector=source_collector, dry_run=options.dry_run))
        for index, packager in enumerate(packagers):
            if index == 0:
                # Clean artifacts from an older folder
                packager.clean_artifact_folder()
            packager.package()
            if options.no_upload is False:
                try:
                    packager.upload(add=add_package, hotfix_release=options.hotfix_release)
                finally:
                    # Always store artifacts in jenkins too
                    packager.prepare_artifact()
