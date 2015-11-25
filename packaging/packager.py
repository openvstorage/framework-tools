# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
