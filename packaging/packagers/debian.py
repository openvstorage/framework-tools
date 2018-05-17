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
Debian packager module
"""
import os
import shutil
from .packager import Packager
from packaging.sourcecollector import SourceCollector


class DebianPackager(Packager):
    """
    DebianPackager class

    Responsible for creating debian packages from the source archive
    """

    def __init__(self, source_collector, dry_run=False):
        """
        Creates an instance of a DebianPacker
        This instance is tied to a SourceCollector instance which holds all product information
        :param source_collector: SourceCollector instance
        :param dry_run: Run the source collector in dry run mode
        * This will not do any impacting changes (like uploading/tagging)
        """
        super(DebianPackager, self).__init__(source_collector, dry_run, distro='debian', package_suffix='.deb')

    def package(self):
        """
        Packages the related product.
        """
        # Validation
        product = self.source_collector.product
        release_repo = self.source_collector.release_repo
        version_string = self.source_collector.version_string
        revision_date = self.source_collector.revision_date
        package_name = self.source_collector.package_name
        if any(item is None for item in [product, release_repo, version_string, revision_date, package_name]):
            raise RuntimeError('The given source collector has not yet collected all of the required information')

        path_code = self.source_collector.path_code
        path_package = self.source_collector.path_package

        # Prepare
        # /<pp>/debian
        if os.path.exists(self.package_folder):
            shutil.rmtree(self.package_folder)
        # /<rp>/packaging/debian -> /<pp>/debian
        shutil.copytree('{0}/packaging/debian'.format(path_code), self.package_folder)

        # Rename tgz
        # /<pp>/<package name>_1.2.3.tar.gz -> /<pp>/debian/<package name>_1.2.3.orig.tar.gz
        shutil.copyfile('{0}/{1}_{2}.tar.gz'.format(path_package, package_name, version_string),
                        '{0}/{1}_{2}.orig.tar.gz'.format(self.package_folder, package_name, version_string))
        # /<pp>/debian/<package name>-1.2.3/...
        SourceCollector.run(command='tar -xzf {0}_{1}.orig.tar.gz'.format(package_name, version_string),
                            working_directory=self.package_folder)

        # Move the debian package metadata into the extracted source
        # /<pp>/debian/debian -> /<pp>/debian/<package name>-1.2.3/
        SourceCollector.run(command='mv {0}/debian {0}/{1}-{2}/'.format(self.package_folder, package_name, version_string),
                            working_directory=path_package)

        # Build changelog entry
        with open('{0}/{1}-{2}/debian/changelog'.format(self.package_folder, package_name, version_string), 'w') as changelog_file:
            changelog_file.write("""{0} ({1}-1) {2}; urgency=low

  * For changes, see individual changelogs

 -- Packaging System <engineering@openvstorage.com>  {3}
""".format(package_name, version_string, release_repo, revision_date.strftime('%a, %d %b %Y %H:%M:%S +0000')))

        # Some more tweaks
        SourceCollector.run(command='chmod 770 {0}/{1}-{2}/debian/rules'.format(self.package_folder, package_name, version_string),
                            working_directory=path_package)
        SourceCollector.run(command="sed -i -e 's/__NEW_VERSION__/{0}/' *.*".format(version_string),
                            working_directory='{0}/{1}-{2}/debian'.format(self.package_folder, package_name, version_string))

        # Build the package
        SourceCollector.run(command='dpkg-buildpackage',
                            working_directory='{0}/{1}-{2}'.format(self.package_folder, package_name, version_string))
        self.packaged = True
