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
    parser.add_option('-s', '--suffix', dest='suffix', default=None)
    parser.add_option('--no-rpm', dest='rpm', action='store_false', default=True)
    parser.add_option('--no-deb', dest='deb', action='store_false', default=True)
    options, args = parser.parse_args()

    # 1. Collect sources
    metadata = SourceCollector.collect(product=options.product,
                                       release=options.release,
                                       revision=options.revision,
                                       suffix=options.suffix)

    if metadata is not None:
        # 2. Build & Upload packages
        if options.deb is True:
            DebianPackager.package(metadata)
            DebianPackager.upload(metadata)
        if options.rpm is True:
            RPMPackager.package(metadata)
            RPMPackager.upload(metadata)
