# Copyright (C) 2018 iNuron NV
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
Pip packager module
"""
import os
import errno
import shutil
from packaging.packagers.debian import DebianPackager
from packaging.sourcecollector import SourceCollector


class PIPDebianPackager(DebianPackager):
    """
    Packages PIP modules to Debian
    ### Pip to Debian
    Change a pip module to a debian package.
    These packages can be included in the repository and can be installed through dependencies

    ### How to
    Requires the py2deb code (https://github.com/paylogic/py2deb)
    #### Installation
    apt-get install python-pip
    pip install py2deb

    #### Usage
    py2deb -r /tmp/py2deb typing  # Installs the typing package under /tmp/py2deb
    """

    def __init__(self, source_collector, dry_run):
        super(PIPDebianPackager, self).__init__(source_collector, dry_run)

    def package(self):
        """
        Packages a PIP module as a package
        """
        # Validation
        product = self.source_collector.product
        release_repo = self.source_collector.release_repo
        if any(item is None for item in [product, release_repo]):
            raise RuntimeError('The given source collector has not yet collected all of the required information')

        if os.path.exists(self.package_folder):
            shutil.rmtree(self.package_folder)

        try:
            # Safer to capture the exception than to check if the directory exists (which can have race condition problems).
            os.makedirs(self.package_folder)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        # Convert using the tool. This will generate a package called python-PRODUCT_VERSION.deb
        # @todo the product has to be substituted with the local directory
        SourceCollector.run('{0} -r {1} {2}'.format(self.source_collector.py2deb_path, self.package_folder, product), working_directory=self.package_folder)
        self.packaged = True
